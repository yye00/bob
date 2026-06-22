"""Tests for F080: Add CLI command show-regressions.

Validates that:
- Step 1: show-regressions command is registered and accessible
- Step 2: Query active_regressions view
- Step 3: Display affected feature, causing feature, status
- Step 4: Test: Show regressions, verify active ones listed
"""

import uuid
from unittest.mock import patch

import pytest
from click.testing import CliRunner


# ============================================================
# Step 1: Add show-regressions command
# ============================================================


class TestShowRegressionsCommandRegistered:
    """Step 1: show-regressions command is registered and accessible."""

    def test_show_regressions_command_registered(self):
        from bob3.cli import main

        assert "show-regressions" in main.commands, "show-regressions command must be registered"

    def test_show_regressions_help_works(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-regressions", "--help"])
        assert result.exit_code == 0
        assert "regression" in result.output.lower()

    def test_show_regressions_uses_rich_table(self):
        """show-regressions should use Rich Table for output."""
        import inspect

        from bob3.cli import show_regressions_cmd

        source = inspect.getsource(show_regressions_cmd.callback)
        assert "Table" in source or "table" in source, \
            "show-regressions should use Rich Table for formatting"


# ============================================================
# Step 2: Query active_regressions view
# ============================================================


class TestShowRegressionsQueryView:
    """Step 2: Queries active_regressions view via db function."""

    def test_calls_query_active_regressions(self):
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=[]) as mock_query, \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        mock_query.assert_called_once_with("proj-1")

    def test_no_project_message(self):
        """Should display a message when no project is found."""
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli._get_current_project_id", return_value=None):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no project" in output_lower


# ============================================================
# Step 3: Display affected feature, causing feature, status
# ============================================================


class TestShowRegressionsDisplay:
    """Step 3: Display affected feature, causing feature, status."""

    def _make_regression_entry(self, affected_name="Auth Module",
                                causing_name="Payment Feature",
                                status="detected", **kwargs):
        base = {
            "id": str(uuid.uuid4()),
            "project_id": "proj-1",
            "affected_feature_id": str(uuid.uuid4()),
            "causing_feature_id": str(uuid.uuid4()),
            "detected_at": "2026-02-20T10:00:00",
            "affected_tests": '["test_auth_login"]',
            "evidence_artifacts": None,
            "status": status,
            "resolution": None,
            "resolved_at": None,
            "affected_feature_name": affected_name,
            "causing_feature_name": causing_name,
        }
        base.update(kwargs)
        return base

    def test_displays_affected_feature_name(self):
        from bob3.cli import main

        entries = [self._make_regression_entry(affected_name="User Auth")]

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        assert "User Auth" in result.output

    def test_displays_causing_feature_name(self):
        from bob3.cli import main

        entries = [self._make_regression_entry(causing_name="Payment Gateway")]

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        assert "Payment Gateway" in result.output

    def test_displays_status(self):
        from bob3.cli import main

        entries = [self._make_regression_entry(status="detected")]

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        assert "detected" in result.output

    def test_no_regressions_message(self):
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=[]), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no active regressions" in output_lower

    def test_displays_multiple_regressions(self):
        from bob3.cli import main

        entries = [
            self._make_regression_entry(affected_name="Auth Module", causing_name="Payment"),
            self._make_regression_entry(affected_name="User Profile", causing_name="Dashboard"),
        ]

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        assert "Auth Module" in result.output
        assert "User Profile" in result.output

    def test_displays_affected_tests(self):
        """Should show affected tests in the output."""
        from bob3.cli import main

        entries = [self._make_regression_entry(
            affected_tests='["test_login", "test_logout"]'
        )]

        runner = CliRunner()
        with patch("bob3.cli.query_active_regressions", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-regressions"])
        assert result.exit_code == 0
        # Should show affected test count or list
        assert "2" in result.output or "test_login" in result.output


# ============================================================
# Step 4: Test: Show regressions, verify active ones listed
# ============================================================


class TestShowRegressionsWithRealData:
    """Step 4: End-to-end test with actual regression data via database."""

    @pytest.fixture()
    def db_with_regressions(self, tmp_path):
        """Create a temporary database with regression events."""
        from bob3.db import get_connection, init_database

        db_path = tmp_path / "test.db"
        init_database(db_path=db_path)

        conn = get_connection(db_path=db_path)
        try:
            # Create a project
            project_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO projects (id, name, workspace_path, status) VALUES (?, ?, ?, ?)",
                (project_id, "test-project", str(tmp_path), "planning"),
            )

            # Create features
            affected_id = str(uuid.uuid4())
            causing_id = str(uuid.uuid4())
            resolved_affected_id = str(uuid.uuid4())
            resolved_causing_id = str(uuid.uuid4())

            for fid, fname in [
                (affected_id, "Auth Module"),
                (causing_id, "Payment Feature"),
                (resolved_affected_id, "Config Module"),
                (resolved_causing_id, "Logging Feature"),
            ]:
                conn.execute(
                    """INSERT INTO features (id, project_id, name, status, priority)
                       VALUES (?, ?, ?, 'pending', 100)""",
                    (fid, project_id, fname),
                )

            # Create active regression (detected - should appear)
            active_reg_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO regression_events
                   (id, project_id, affected_feature_id, causing_feature_id,
                    detected_at, affected_tests, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (active_reg_id, project_id, affected_id, causing_id,
                 "2026-02-20T10:00:00", '["test_auth_login"]', "detected"),
            )

            # Create resolved regression (should NOT appear in active view)
            resolved_reg_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO regression_events
                   (id, project_id, affected_feature_id, causing_feature_id,
                    detected_at, affected_tests, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (resolved_reg_id, project_id, resolved_affected_id, resolved_causing_id,
                 "2026-02-19T10:00:00", '["test_config"]', "resolved"),
            )

            conn.commit()
        finally:
            conn.close()

        return db_path, project_id

    def test_show_regressions_with_real_db(self, db_with_regressions):
        """Full integration: show-regressions with actual database data."""
        from bob3.cli import main
        from bob3.db import query_active_regressions

        db_path, project_id = db_with_regressions

        # First verify the view returns data
        with patch("bob3.db.get_database_path", return_value=db_path):
            regressions = query_active_regressions(project_id)

        assert len(regressions) == 1, "Should have exactly 1 active regression (resolved is filtered)"
        assert regressions[0]["affected_feature_name"] == "Auth Module"

        # Now test the CLI command with the real data
        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=db_path), \
             patch("bob3.cli._get_current_project_id", return_value=project_id), \
             patch("bob3.cli.query_active_regressions", wraps=query_active_regressions) as mock_query:
            result = runner.invoke(main, ["show-regressions"])

        assert result.exit_code == 0
        mock_query.assert_called_once_with(project_id)

        # Active regression should appear
        assert "Auth Module" in result.output
        assert "Payment Feature" in result.output

        # Resolved regression should NOT appear
        assert "Config Module" not in result.output

    def test_only_active_regressions_shown(self, db_with_regressions):
        """Resolved regressions should be filtered out."""
        from bob3.db import query_active_regressions

        db_path, project_id = db_with_regressions

        with patch("bob3.db.get_database_path", return_value=db_path):
            regressions = query_active_regressions(project_id)

        # Only the active (detected) regression should be returned
        assert len(regressions) == 1
        assert regressions[0]["status"] == "detected"
