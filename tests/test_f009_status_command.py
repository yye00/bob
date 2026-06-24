"""Tests for F009: Implement 'bob3 status' command to show project status."""

import pathlib
import sqlite3
import uuid

import pytest
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


def _init_project(tmp_path, name="test-project"):
    """Helper: create an initialized project and return (project_path, db_path)."""
    from bob3.cli import main

    project_path = tmp_path / name
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(project_path)])
    assert result.exit_code == 0, f"init failed: {result.output}"
    db_path = project_path / "bob3.db"
    return project_path, db_path


def _add_features(db_path, project_id, features):
    """Helper: insert features into the database.

    features is a list of (id, name, status) tuples.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    for fid, fname, fstatus in features:
        conn.execute(
            "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
            (fid, project_id, fname, fstatus),
        )
    conn.commit()
    conn.close()


def _get_project_id(db_path):
    """Helper: retrieve the first project ID from the database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT id FROM projects LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def _set_project_cost(db_path, project_id, total_cost, max_cost=500.0):
    """Helper: set cost values on the project record."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE projects SET total_cost_usd = ?, max_cost_usd = ? WHERE id = ?",
        (total_cost, max_cost, project_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# Step 1: Implement status command in cli.py
# ============================================================


class TestStatusCommandExists:
    """Step 1: Status command is registered and callable."""

    def test_status_command_registered(self):
        from bob3.cli import main

        assert "status" in main.commands, "status command must be registered"

    def test_status_runs_without_error(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status command failed: {result.output}"

    def test_status_help_works(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output.lower() or "project" in result.output.lower()


# ============================================================
# Step 2: Query database for project info
# ============================================================


class TestStatusQueriesDatabase:
    """Step 2: Status command queries database for project information."""

    def test_status_shows_project_name(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path, name="my-cool-project")
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "my-cool-project" in result.output, (
            f"Project name not in output: {result.output}"
        )

    def test_status_shows_project_status(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "planning" in result.output.lower(), (
            f"Project status 'planning' not in output: {result.output}"
        )

    def test_status_no_project_shows_message(self, tmp_path):
        """If database has no project, show a helpful message."""
        from bob3.cli import main
        from bob3.db import init_database

        db_path = tmp_path / "empty.db"
        init_database(db_path=db_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "no project" in result.output.lower() or "not found" in result.output.lower(), (
            f"Expected 'no project' message, got: {result.output}"
        )


# ============================================================
# Step 3: Show feature counts by status
# ============================================================


class TestStatusFeatureCounts:
    """Step 3: Status command shows feature counts grouped by status."""

    def test_status_shows_feature_summary(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Feature A", "completed"),
                (str(uuid.uuid4()), "Feature B", "completed"),
                (str(uuid.uuid4()), "Feature C", "pending"),
                (str(uuid.uuid4()), "Feature D", "executing"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        # Should show total features
        assert "4" in result.output, f"Expected total feature count '4' in output: {result.output}"

    def test_status_shows_completed_count(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Feature A", "completed"),
                (str(uuid.uuid4()), "Feature B", "completed"),
                (str(uuid.uuid4()), "Feature C", "pending"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        # Should show "completed" count somewhere
        assert "completed" in result.output.lower(), (
            f"'completed' not in output: {result.output}"
        )
        assert "2" in result.output, (
            f"Expected completed count '2' in output: {result.output}"
        )

    def test_status_shows_pending_count(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Feature A", "pending"),
                (str(uuid.uuid4()), "Feature B", "pending"),
                (str(uuid.uuid4()), "Feature C", "pending"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "pending" in result.output.lower(), (
            f"'pending' not in output: {result.output}"
        )

    def test_status_no_features_shows_zero(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "0" in result.output, (
            f"Expected '0' for no features in output: {result.output}"
        )


# ============================================================
# Step 4: Show resource usage (cost)
# ============================================================


class TestStatusResourceUsage:
    """Step 4: Status command shows resource usage (cost)."""

    def test_status_shows_cost(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=12.50, max_cost=500.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "12.50" in result.output, (
            f"Expected cost '12.50' in output: {result.output}"
        )

    def test_status_shows_max_cost(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=50.0, max_cost=200.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        assert "200.00" in result.output, (
            f"Expected max cost '200.00' in output: {result.output}"
        )

    def test_status_shows_cost_label(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        output_lower = result.output.lower()
        assert "cost" in output_lower, f"Expected 'cost' label in output: {result.output}"


# ============================================================
# Step 5: Use Rich library for formatted output
# ============================================================


class TestStatusUsesRich:
    """Step 5: Status command uses Rich library for formatted output."""

    def test_status_uses_rich_import(self):
        """The cli module should import from rich."""
        import bob3.cli
        import inspect

        source = inspect.getsource(bob3.cli)
        assert "rich" in source.lower(), "cli.py should use Rich library"

    def test_status_output_is_not_empty(self, tmp_path):
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0, "Status output should not be empty"


# ============================================================
# Step 6: Run 'bob3 status' and verify output format
# ============================================================


class TestStatusEndToEnd:
    """Step 6: End-to-end test of the full status output."""

    def test_full_status_output(self, tmp_path):
        """Status with features and cost shows complete formatted output."""
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path, name="e2e-project")
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Database Schema", "completed"),
                (str(uuid.uuid4()), "Data Models", "completed"),
                (str(uuid.uuid4()), "CLI Framework", "executing"),
                (str(uuid.uuid4()), "Status Command", "pending"),
                (str(uuid.uuid4()), "Run Command", "pending"),
            ],
        )
        _set_project_cost(db_path, project_id, total_cost=25.75, max_cost=100.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB3_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"status failed: {result.output}"

        output = result.output
        # Verify project name
        assert "e2e-project" in output, f"Project name missing: {output}"
        # Verify cost display
        assert "25.75" in output, f"Cost missing: {output}"
        # Verify feature counts (5 total)
        assert "5" in output, f"Total feature count missing: {output}"
        # Verify status labels present
        output_lower = output.lower()
        assert "completed" in output_lower, f"'completed' label missing: {output}"

    def test_status_with_feature_flag(self, tmp_path):
        """Status with --feature flag shows specific feature info."""
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = str(uuid.uuid4())
        _add_features(
            db_path,
            project_id,
            [(feature_id, "Specific Feature", "executing")],
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status", "--feature", feature_id],
            env={"BOB3_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0, f"status --feature failed: {result.output}"
        assert "Specific Feature" in result.output, (
            f"Feature name not in output: {result.output}"
        )

    def test_status_with_verbose_flag(self, tmp_path):
        """Status with --verbose flag shows additional detail."""
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Feature X", "completed"),
                (str(uuid.uuid4()), "Feature Y", "pending"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status", "--verbose"],
            env={"BOB3_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0, f"status --verbose failed: {result.output}"
        # Verbose mode should show individual feature names
        assert "Feature X" in result.output, f"Feature X not in verbose output: {result.output}"
        assert "Feature Y" in result.output, f"Feature Y not in verbose output: {result.output}"

    def test_status_feature_not_found(self, tmp_path):
        """Status with --feature for a non-existent feature shows helpful message."""
        from bob3.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status", "--feature", "nonexistent-id"],
            env={"BOB3_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0, f"status failed: {result.output}"
        output_lower = result.output.lower()
        assert "not found" in output_lower or "no feature" in output_lower, (
            f"Expected 'not found' message, got: {result.output}"
        )
