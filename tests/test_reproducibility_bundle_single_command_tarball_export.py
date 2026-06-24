"""Tests for the reproducibility bundle single-command tarball export feature.

Verifies:
- The export_bundle() public API in the feature module
- The `bob bundle --run-id <id>` CLI command end-to-end
- Self-contained bundle contents (manifest, spec, transcript, diff, telemetry, lockfile)
- Feature-ID resolution to latest agent run
- Error handling for unknown run IDs
"""

import json
import pathlib
import sqlite3
import tarfile
import uuid

import pytest
from click.testing import CliRunner

from bob.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_db(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal bob.db with schema for bundle tests."""
    from bob.db import init_database

    db_path = tmp_path / "bob.db"
    init_database(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, status) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), "test-project", str(tmp_path), "executing"),
    )
    conn.commit()
    conn.close()
    return db_path


def _insert_agent_run(
    db_path: pathlib.Path,
    project_id: str | None = None,
    run_id: str | None = None,
    feature_id: str | None = None,
) -> str:
    """Insert a sub_agent_run record and return its id."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if project_id is None:
        row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        project_id = row["id"]
    rid = run_id or str(uuid.uuid4())
    fid = feature_id or str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sub_agent_runs
           (id, project_id, purpose, target_type, target_id, status,
            prompt_summary, result_summary, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (
            rid, project_id, "implement_feature", "feature", fid, "completed",
            "Implement reproducibility bundle", "Bundle exported successfully",
        ),
    )
    conn.commit()
    conn.close()
    return rid


def _open_member(tar: tarfile.TarFile, suffix: str) -> bytes:
    """Extract and return bytes from the first tar member whose name ends with suffix."""
    member = next(m for m in tar.getmembers() if m.name.endswith(suffix))
    return tar.extractfile(member).read()


# ---------------------------------------------------------------------------
# Module-level API tests
# ---------------------------------------------------------------------------


class TestExportBundleAPI:
    def test_export_bundle_returns_path(self, tmp_path, monkeypatch):
        """export_bundle returns a pathlib.Path that exists on disk."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        result = export_bundle(run_id=run_id, output_dir=tmp_path)

        assert isinstance(result, pathlib.Path)
        assert result.exists()

    def test_export_bundle_produces_tarball(self, tmp_path, monkeypatch):
        """export_bundle produces a valid .tar.gz archive."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        result = export_bundle(run_id=run_id, output_dir=tmp_path)

        assert result.suffix == ".gz"
        assert tarfile.is_tarfile(str(result))

    def test_export_bundle_contains_all_required_files(self, tmp_path, monkeypatch):
        """Bundle tarball must contain all self-contained artifacts."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(run_id=run_id, output_dir=tmp_path)

        required = {"manifest.json", "spec.yaml", "transcript.txt", "diff.patch",
                    "telemetry.jsonl", "env_lockfile.txt"}

        with tarfile.open(bundle_path, "r:gz") as tar:
            names = {pathlib.Path(m.name).name for m in tar.getmembers() if m.isfile()}

        assert required.issubset(names), f"Missing: {required - names}"

    def test_manifest_records_run_id(self, tmp_path, monkeypatch):
        """manifest.json inside the bundle records the run_id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(run_id=run_id, output_dir=tmp_path)

        with tarfile.open(bundle_path, "r:gz") as tar:
            manifest = json.loads(_open_member(tar, "manifest.json"))

        assert manifest["run_id"] == run_id
        assert "bundle_version" in manifest
        assert "created_at" in manifest

    def test_env_lockfile_lists_packages(self, tmp_path, monkeypatch):
        """env_lockfile.txt must be non-empty (lists installed packages)."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(run_id=run_id, output_dir=tmp_path)

        with tarfile.open(bundle_path, "r:gz") as tar:
            lockfile = _open_member(tar, "env_lockfile.txt").decode("utf-8")

        assert len(lockfile.strip()) > 0

    def test_transcript_contains_run_status(self, tmp_path, monkeypatch):
        """transcript.txt must mention the run status or run ID."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(run_id=run_id, output_dir=tmp_path)

        with tarfile.open(bundle_path, "r:gz") as tar:
            transcript = _open_member(tar, "transcript.txt").decode("utf-8")

        assert "completed" in transcript.lower() or run_id[:8] in transcript

    def test_invalid_run_id_raises_value_error(self, tmp_path, monkeypatch):
        """export_bundle raises ValueError for an unknown run_id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        with pytest.raises(ValueError, match="not found"):
            export_bundle(run_id="no-such-run", output_dir=tmp_path)

    def test_feature_id_resolves_to_latest_run(self, tmp_path, monkeypatch):
        """Passing a feature_id resolves to the most recent agent run."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        feature_id = str(uuid.uuid4())
        _insert_agent_run(db_path, feature_id=feature_id)

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(run_id=feature_id, output_dir=tmp_path)
        assert bundle_path.exists()

        with tarfile.open(bundle_path, "r:gz") as tar:
            manifest = json.loads(_open_member(tar, "manifest.json"))

        assert manifest["original_run_id_arg"] == feature_id

    def test_telemetry_filters_matching_run(self, tmp_path, monkeypatch):
        """Telemetry in bundle contains only lines matching the run_id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        bob_dir = tmp_path / ".bob"
        bob_dir.mkdir(exist_ok=True)
        run_jsonl_path = bob_dir / "run.jsonl"
        matching = {"run_id": run_id, "cost_usd": 0.12}
        unrelated = {"run_id": "other-run", "cost_usd": 0.99}
        with run_jsonl_path.open("w") as f:
            f.write(json.dumps(matching) + "\n")
            f.write(json.dumps(unrelated) + "\n")

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(
            run_id=run_id, output_dir=tmp_path, run_jsonl_path=run_jsonl_path
        )

        with tarfile.open(bundle_path, "r:gz") as tar:
            telemetry = _open_member(tar, "telemetry.jsonl").decode("utf-8")

        assert run_id in telemetry
        assert "other-run" not in telemetry

    def test_output_dir_created_automatically(self, tmp_path, monkeypatch):
        """export_bundle creates output_dir if it doesn't exist."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)
        new_dir = tmp_path / "deep" / "bundles"
        assert not new_dir.exists()

        from bob.reproducibility_bundle_single_command_tarball_export import export_bundle

        bundle_path = export_bundle(run_id=run_id, output_dir=new_dir)
        assert bundle_path.exists()
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestBundleCommandCLI:
    def test_bundle_command_registered(self):
        """The `bundle` subcommand is registered in the CLI."""
        runner = CliRunner()
        result = runner.invoke(main, ["bundle", "--help"])
        assert result.exit_code == 0
        assert "--run-id" in result.output

    def test_bundle_command_creates_tarball(self, tmp_path, monkeypatch):
        """CLI `bundle --run-id` creates a .tar.gz in the output directory."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["bundle", "--run-id", run_id, "--output-dir", str(tmp_path)],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert "Bundle created" in result.output

        bundles = list(tmp_path.glob("bundle_*.tar.gz"))
        assert len(bundles) == 1

    def test_bundle_command_invalid_run_id(self, tmp_path, monkeypatch):
        """CLI exits with code 1 for an unknown run-id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["bundle", "--run-id", "totally-fake-run-id", "--output-dir", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "Error" in result.output or "not found" in result.output

    def test_bundle_command_requires_run_id(self):
        """CLI `bundle` without --run-id exits with non-zero code."""
        runner = CliRunner()
        result = runner.invoke(main, ["bundle"])
        assert result.exit_code != 0
        assert "run-id" in result.output.lower() or "missing" in result.output.lower()

    def test_bundle_command_output_mentions_path(self, tmp_path, monkeypatch):
        """CLI output mentions the bundle file path after creation."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["bundle", "--run-id", run_id, "--output-dir", str(tmp_path)],
        )

        assert result.exit_code == 0
        # The output should reference "bundle_" which is in the filename
        assert "bundle_" in result.output
