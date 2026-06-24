"""Tests for F076: Add CLI commands list-features and show-feature."""

import json
import pathlib
import sqlite3

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


def _add_features(db_path, project_id, features):
    """Helper: insert features into the database.

    features is a list of (id, name, status, priority, description) tuples.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    for fid, fname, fstatus, fpriority, fdesc in features:
        conn.execute(
            "INSERT INTO features (id, project_id, name, status, priority, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fid, project_id, fname, fstatus, fpriority, fdesc),
        )
    conn.commit()
    conn.close()


# ============================================================
# Step 1: Add list-features command to show all features
# ============================================================


class TestListFeaturesCommand:
    """Step 1: list-features command is registered and works."""

    def test_list_features_command_registered(self):
        from bob.cli import main

        assert "list-features" in main.commands, "list-features command must be registered"

    def test_list_features_help_works(self):
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["list-features", "--help"])
        assert result.exit_code == 0
        assert "feature" in result.output.lower()

    def test_list_features_shows_all_features(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        _add_features(db_path, project_id, [
            ("f1", "Database Schema", "completed", 10, "Create DB schema"),
            ("f2", "CLI Framework", "ready", 20, "Setup Click CLI"),
            ("f3", "API Endpoints", "pending", 30, "REST API endpoints"),
        ])

        runner = CliRunner()
        result = runner.invoke(
            main, ["list-features"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0, f"list-features failed: {result.output}"
        assert "Database Schema" in result.output
        assert "CLI Framework" in result.output
        assert "API Endpoints" in result.output

    def test_list_features_shows_status(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        _add_features(db_path, project_id, [
            ("f1", "Feature A", "completed", 10, "Desc A"),
            ("f2", "Feature B", "pending", 20, "Desc B"),
        ])

        runner = CliRunner()
        result = runner.invoke(
            main, ["list-features"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "completed" in result.output
        assert "pending" in result.output

    def test_list_features_filter_by_status(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        _add_features(db_path, project_id, [
            ("f1", "Feature A", "completed", 10, "Desc A"),
            ("f2", "Feature B", "pending", 20, "Desc B"),
            ("f3", "Feature C", "completed", 30, "Desc C"),
        ])

        runner = CliRunner()
        result = runner.invoke(
            main, ["list-features", "--status", "completed"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "Feature A" in result.output
        assert "Feature C" in result.output
        assert "Feature B" not in result.output

    def test_list_features_empty_project(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main, ["list-features"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "no features" in result.output.lower() or "0" in result.output


# ============================================================
# Step 2: Add show-feature command to show feature details
# ============================================================


class TestShowFeatureCommand:
    """Step 2: show-feature command shows detailed feature information."""

    def test_show_feature_command_registered(self):
        from bob.cli import main

        assert "show-feature" in main.commands, "show-feature command must be registered"

    def test_show_feature_help_works(self):
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-feature", "--help"])
        assert result.exit_code == 0

    def test_show_feature_displays_details(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        _add_features(db_path, project_id, [
            ("feat-001", "Database Schema", "completed", 10, "Create the DB schema"),
        ])

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-feature", "feat-001"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0, f"show-feature failed: {result.output}"
        assert "Database Schema" in result.output
        assert "feat-001" in result.output
        assert "completed" in result.output

    def test_show_feature_displays_confidence_scores(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        # Insert feature with confidence scores
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """INSERT INTO features (id, project_id, name, status, priority,
               conf_spec_understanding, conf_impl_correctness, conf_test_adequacy,
               readiness_score, risk_category)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("feat-002", project_id, "API Layer", "ready", 20,
             0.85, 0.70, 0.60, 0.72, "high"),
        )
        conn.commit()
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-feature", "feat-002"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "0.85" in result.output
        assert "0.70" in result.output
        assert "0.60" in result.output
        assert "high" in result.output

    def test_show_feature_not_found(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-feature", "nonexistent-id"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_show_feature_displays_acceptance_criteria(self, tmp_path):
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        criteria = json.dumps(["Tests pass", "Coverage > 80%"])
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO features (id, project_id, name, status, acceptance_criteria) "
            "VALUES (?, ?, ?, ?, ?)",
            ("feat-003", project_id, "Testing", "pending", criteria),
        )
        conn.commit()
        conn.close()

        runner = CliRunner()
        result = runner.invoke(
            main, ["show-feature", "feat-003"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "Tests pass" in result.output
        assert "Coverage > 80%" in result.output


# ============================================================
# Step 3: Use Rich for formatting
# ============================================================


class TestRichFormatting:
    """Step 3: Both commands use Rich for formatted output."""

    def test_list_features_uses_rich_table(self):
        """Verify the list-features command uses Rich Table."""
        import inspect
        from bob.cli import list_features_cmd

        source = inspect.getsource(list_features_cmd.callback)
        assert "Table" in source or "table" in source, \
            "list-features should use Rich Table for formatting"

    def test_show_feature_uses_rich(self):
        """Verify the show-feature command uses Rich."""
        import inspect
        from bob.cli import show_feature

        source = inspect.getsource(show_feature.callback)
        assert "Table" in source or "Console" in source or "console" in source, \
            "show-feature should use Rich for formatting"


# ============================================================
# Step 4: Integration - List features, show specific feature
# ============================================================


class TestIntegration:
    """Step 4: End-to-end integration of list and show commands."""

    def test_list_then_show_workflow(self, tmp_path):
        """List features then show details for one."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        _add_features(db_path, project_id, [
            ("feat-alpha", "Alpha Feature", "completed", 10, "First feature"),
            ("feat-beta", "Beta Feature", "ready", 20, "Second feature"),
        ])

        runner = CliRunner()

        # List all features
        list_result = runner.invoke(
            main, ["list-features"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert list_result.exit_code == 0
        assert "Alpha Feature" in list_result.output
        assert "Beta Feature" in list_result.output

        # Show specific feature details
        show_result = runner.invoke(
            main, ["show-feature", "feat-alpha"],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert show_result.exit_code == 0
        assert "Alpha Feature" in show_result.output
        assert "completed" in show_result.output

    def test_list_features_ordered_by_priority(self, tmp_path):
        """Features should appear ordered by priority."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)

        _add_features(db_path, project_id, [
            ("f-low", "Low Priority", "pending", 300, "Low"),
            ("f-high", "High Priority", "pending", 10, "High"),
            ("f-mid", "Mid Priority", "pending", 100, "Mid"),
        ])

        runner = CliRunner()
        result = runner.invoke(
            main, ["list-features"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        # High priority should appear before Low priority
        high_pos = result.output.index("High Priority")
        mid_pos = result.output.index("Mid Priority")
        low_pos = result.output.index("Low Priority")
        assert high_pos < mid_pos < low_pos
