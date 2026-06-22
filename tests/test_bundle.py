"""Tests for the reproducibility bundle exporter (bob3 bundle --run-id)."""

import json
import pathlib
import sqlite3
import tarfile
import tempfile
import uuid

import pytest
from click.testing import CliRunner

from bob3.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_db(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal bob3.db with schema needed for bundle tests."""
    from bob3.db import init_database

    db_path = tmp_path / "bob3.db"
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
            "Implement bundle feature", "Bundle created successfully",
        ),
    )
    conn.commit()
    conn.close()
    return rid


# ---------------------------------------------------------------------------
# Unit tests for bob3.bundle module
# ---------------------------------------------------------------------------


class TestCreateBundle:
    def test_creates_tarball(self, tmp_path, monkeypatch):
        """create_bundle returns a .tar.gz path that actually exists."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(run_id=run_id, output_dir=tmp_path)

        assert bundle_path.exists()
        assert bundle_path.suffix == ".gz"
        assert "bundle_" in bundle_path.name

    def test_tarball_contains_required_files(self, tmp_path, monkeypatch):
        """Bundle tarball must contain all required artifact files."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(run_id=run_id, output_dir=tmp_path)

        required_files = {
            "manifest.json",
            "spec.yaml",
            "transcript.txt",
            "diff.patch",
            "telemetry.jsonl",
            "env_lockfile.txt",
        }

        with tarfile.open(bundle_path, "r:gz") as tar:
            member_names = {pathlib.Path(m.name).name for m in tar.getmembers() if m.isfile()}

        assert required_files.issubset(member_names), (
            f"Missing files: {required_files - member_names}"
        )

    def test_manifest_contains_run_id(self, tmp_path, monkeypatch):
        """manifest.json inside the bundle must record the resolved run_id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(run_id=run_id, output_dir=tmp_path)

        with tarfile.open(bundle_path, "r:gz") as tar:
            manifest_member = next(
                m for m in tar.getmembers() if m.name.endswith("manifest.json")
            )
            manifest_bytes = tar.extractfile(manifest_member).read()

        manifest = json.loads(manifest_bytes)
        assert manifest["run_id"] == run_id
        assert "created_at" in manifest
        assert "bundle_version" in manifest

    def test_transcript_contains_run_info(self, tmp_path, monkeypatch):
        """transcript.txt must mention the run status."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(run_id=run_id, output_dir=tmp_path)

        with tarfile.open(bundle_path, "r:gz") as tar:
            tx_member = next(
                m for m in tar.getmembers() if m.name.endswith("transcript.txt")
            )
            transcript = tar.extractfile(tx_member).read().decode("utf-8")

        assert "completed" in transcript.lower() or run_id[:8] in transcript

    def test_env_lockfile_not_empty(self, tmp_path, monkeypatch):
        """env_lockfile.txt must not be empty — should list installed packages."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(run_id=run_id, output_dir=tmp_path)

        with tarfile.open(bundle_path, "r:gz") as tar:
            lock_member = next(
                m for m in tar.getmembers() if m.name.endswith("env_lockfile.txt")
            )
            lock_content = tar.extractfile(lock_member).read().decode("utf-8")

        assert len(lock_content.strip()) > 0

    def test_invalid_run_id_raises_value_error(self, tmp_path, monkeypatch):
        """create_bundle must raise ValueError for an unknown run_id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        from bob3.bundle import create_bundle

        with pytest.raises(ValueError, match="not found"):
            create_bundle(run_id="nonexistent-run-id", output_dir=tmp_path)

    def test_feature_id_resolves_to_agent_run(self, tmp_path, monkeypatch):
        """Passing a feature_id instead of a run_id resolves to the latest agent run."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        feature_id = str(uuid.uuid4())
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        project_id = row[0]
        conn.close()

        # Insert an agent run for this feature
        _insert_agent_run(db_path, project_id=project_id, feature_id=feature_id)

        from bob3.bundle import create_bundle

        # Passing the feature_id — bundle should resolve to the agent run
        bundle_path = create_bundle(run_id=feature_id, output_dir=tmp_path)
        assert bundle_path.exists()

        with tarfile.open(bundle_path, "r:gz") as tar:
            manifest_member = next(
                m for m in tar.getmembers() if m.name.endswith("manifest.json")
            )
            manifest = json.loads(tar.extractfile(manifest_member).read())

        assert manifest["original_run_id_arg"] == feature_id

    def test_telemetry_extracted_from_run_jsonl(self, tmp_path, monkeypatch):
        """Telemetry matching the run_id is extracted into telemetry.jsonl."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)

        # Write a fake run.jsonl with a matching entry
        bob3_dir = tmp_path / ".bob3"
        bob3_dir.mkdir(exist_ok=True)
        run_jsonl_path = bob3_dir / "run.jsonl"
        telemetry_record = {"run_id": run_id, "completion_status": "completed", "cost_usd": 0.42}
        other_record = {"run_id": "other-run", "completion_status": "failed"}
        with run_jsonl_path.open("w") as f:
            f.write(json.dumps(telemetry_record) + "\n")
            f.write(json.dumps(other_record) + "\n")

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(
            run_id=run_id, output_dir=tmp_path, run_jsonl_path=run_jsonl_path
        )

        with tarfile.open(bundle_path, "r:gz") as tar:
            telem_member = next(
                m for m in tar.getmembers() if m.name.endswith("telemetry.jsonl")
            )
            telem_content = tar.extractfile(telem_member).read().decode("utf-8")

        # Should contain the matching line but not the unrelated one
        assert run_id in telem_content
        assert "other-run" not in telem_content

    def test_output_dir_created_if_missing(self, tmp_path, monkeypatch):
        """create_bundle creates the output directory if it doesn't exist."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)
        new_output_dir = tmp_path / "new_subdir" / "bundles"
        assert not new_output_dir.exists()

        from bob3.bundle import create_bundle

        bundle_path = create_bundle(run_id=run_id, output_dir=new_output_dir)
        assert bundle_path.exists()
        assert new_output_dir.exists()


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestBundleCLI:
    def test_cli_bundle_command_exists(self):
        """The 'bundle' subcommand is registered in the CLI."""
        runner = CliRunner()
        result = runner.invoke(main, ["bundle", "--help"])
        assert result.exit_code == 0
        assert "--run-id" in result.output

    def test_cli_bundle_creates_file(self, tmp_path, monkeypatch):
        """CLI bundle command creates a bundle file in the specified directory."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        run_id = _insert_agent_run(db_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["bundle", "--run-id", run_id, "--output-dir", str(tmp_path)],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert "Bundle created" in result.output

        # Verify a .tar.gz file was created in tmp_path
        bundles = list(tmp_path.glob("bundle_*.tar.gz"))
        assert len(bundles) == 1

    def test_cli_bundle_invalid_run_id_exits_1(self, tmp_path, monkeypatch):
        """CLI exits with code 1 for an unknown run-id."""
        db_path = _make_temp_db(tmp_path)
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["bundle", "--run-id", "totally-fake-id", "--output-dir", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "Error" in result.output or "not found" in result.output

    def test_cli_bundle_requires_run_id(self):
        """CLI bundle command requires --run-id option."""
        runner = CliRunner()
        result = runner.invoke(main, ["bundle"])
        assert result.exit_code != 0
        assert "run-id" in result.output.lower() or "missing" in result.output.lower()
