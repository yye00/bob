"""Tests for F077: Add CLI command show-evidence <feature_id>."""

import json
import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


def _init_project(tmp_path, name="test-project"):
    """Helper: create an initialized project and return (project_path, db_path)."""
    from bob.cli import main

    project_path = tmp_path / name
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(project_path)])
    assert result.exit_code == 0, f"init failed: {result.output}"
    db_path = project_path / "bob.db"
    return project_path, db_path


def _get_project_id(db_path):
    """Helper: retrieve the first project ID from the database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT id FROM projects LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def _add_feature(db_path, project_id, feature_id, name="Test Feature", status="ready"):
    """Helper: insert a feature into the database."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
        (feature_id, project_id, name, status),
    )
    conn.commit()
    conn.close()


def _add_evidence(db_path, project_id, feature_id, evidence_id, evidence_type, content,
                  verification_passed=None, is_current=True):
    """Helper: insert an evidence artifact into the database."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO evidence_artifacts
           (id, project_id, feature_id, type, content, verification_passed,
            is_current, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (evidence_id, project_id, feature_id, evidence_type, content,
         verification_passed, is_current, now),
    )
    conn.commit()
    conn.close()


# ============================================================
# Step 1: Add show-evidence command
# ============================================================


class TestShowEvidenceCommandRegistered:
    """Step 1: show-evidence command is registered and accessible."""

    def test_show_evidence_command_registered(self):
        from bob.cli import main

        assert "show-evidence" in main.commands, "show-evidence command must be registered"

    def test_show_evidence_help_works(self):
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-evidence", "--help"])
        assert result.exit_code == 0
        assert "evidence" in result.output.lower()

    def test_show_evidence_requires_feature_id_argument(self):
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-evidence"])
        # Should fail because FEATURE_ID argument is missing
        assert result.exit_code != 0


# ============================================================
# Step 2: Query evidence_artifacts for feature
# ============================================================


class TestShowEvidenceQueriesDB:
    """Step 2: show-evidence queries evidence_artifacts for the given feature."""

    def test_show_evidence_for_feature_with_evidence(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-001"

        _add_feature(db_path, project_id, feature_id, "Database Schema")
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-001", "test_output", "All 5 tests passed",
            verification_passed=True,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0, f"show-evidence failed: {result.output}"
        assert "test_output" in result.output
        assert "All 5 tests passed" in result.output

    def test_show_evidence_feature_not_found(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", "nonexistent-feature"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "no evidence" in result.output.lower() or "not found" in result.output.lower()

    def test_show_evidence_no_evidence_for_feature(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-empty"

        _add_feature(db_path, project_id, feature_id, "Empty Feature")

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "no evidence" in result.output.lower()


# ============================================================
# Step 3: Display evidence type, content summary, verification status
# ============================================================


class TestShowEvidenceDisplay:
    """Step 3: Display shows evidence type, content summary, and verification status."""

    def test_displays_evidence_type(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-typed"

        _add_feature(db_path, project_id, feature_id, "Typed Feature")
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-type", "test_output", "Tests passed",
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "test_output" in result.output

    def test_displays_content_summary(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-content"

        _add_feature(db_path, project_id, feature_id, "Content Feature")
        long_content = "A" * 200
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-long", "build_log", long_content,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        # Content should be truncated/summarized (not the full 200 chars)
        # At minimum it should show some of the content
        assert "AAA" in result.output

    def test_displays_verification_status_passed(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-verified"

        _add_feature(db_path, project_id, feature_id, "Verified Feature")
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-pass", "test_output", "All passed",
            verification_passed=True,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        # Should show verification status
        output_lower = result.output.lower()
        assert "pass" in output_lower or "yes" in output_lower or "✓" in result.output

    def test_displays_verification_status_failed(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-failed"

        _add_feature(db_path, project_id, feature_id, "Failed Feature")
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-fail", "test_output", "Tests failed",
            verification_passed=False,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "fail" in output_lower or "no" in output_lower or "✗" in result.output

    def test_displays_verification_status_unknown(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-unk"

        _add_feature(db_path, project_id, feature_id, "Unknown Feature")
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-unk", "test_output", "Some output",
            verification_passed=None,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        # Should handle None verification gracefully
        assert result.exit_code == 0


# ============================================================
# Step 4: Test with feature having multiple artifacts
# ============================================================


class TestShowEvidenceMultipleArtifacts:
    """Step 4: Show evidence for a feature with multiple artifacts."""

    def test_shows_multiple_evidence_artifacts(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-multi"

        _add_feature(db_path, project_id, feature_id, "Multi-evidence Feature")

        _add_evidence(
            db_path, project_id, feature_id,
            "ev-1", "test_output", "Unit tests: 10/10 passed",
            verification_passed=True,
        )
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-2", "build_log", "Build completed successfully",
            verification_passed=True,
        )
        _add_evidence(
            db_path, project_id, feature_id,
            "ev-3", "screenshot", "Screenshot of UI rendering",
            verification_passed=None,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0, f"show-evidence failed: {result.output}"

        # All three evidence types should appear
        assert "test_output" in result.output
        assert "build_log" in result.output
        assert "screenshot" in result.output

        # Content summaries should appear
        assert "Unit tests" in result.output
        assert "Build completed" in result.output
        assert "Screenshot of UI" in result.output

    def test_shows_evidence_count(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = "feat-count"

        _add_feature(db_path, project_id, feature_id, "Count Feature")

        for i in range(3):
            _add_evidence(
                db_path, project_id, feature_id,
                f"ev-c{i}", "test_output", f"Test run {i}",
            )

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-evidence", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        # Should indicate the count of evidence artifacts
        assert "3" in result.output

    def test_uses_rich_table(self):
        """Verify the show-evidence command uses Rich Table for output."""
        import inspect
        from bob.cli import show_evidence_cmd

        source = inspect.getsource(show_evidence_cmd.callback)
        assert "Table" in source or "table" in source, \
            "show-evidence should use Rich Table for formatting"
