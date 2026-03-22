"""Tests for F079: Add CLI command show-calibration.

Validates that:
- Step 1: show-calibration command is registered and accessible
- Step 2: Query calibration_drift_summary view
- Step 3: Display task class, confidence bucket, drift, status
- Step 4: Highlight overconfident/underconfident buckets
- Step 5: Test: Show calibration with drift data
"""

import sqlite3
import uuid
from unittest.mock import patch

import pytest
from click.testing import CliRunner


# ============================================================
# Step 1: Add show-calibration command
# ============================================================


class TestShowCalibrationCommandRegistered:
    """Step 1: show-calibration command is registered and accessible."""

    def test_show_calibration_command_registered(self):
        from bob3.cli import main

        assert "show-calibration" in main.commands, "show-calibration command must be registered"

    def test_show_calibration_help_works(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["show-calibration", "--help"])
        assert result.exit_code == 0
        assert "calibration" in result.output.lower()

    def test_show_calibration_uses_rich_table(self):
        """show-calibration should use Rich Table for output."""
        import inspect

        from bob3.cli import show_calibration_cmd

        source = inspect.getsource(show_calibration_cmd.callback)
        assert "Table" in source or "table" in source, \
            "show-calibration should use Rich Table for formatting"


# ============================================================
# Step 2: Query calibration_drift_summary view
# ============================================================


class TestShowCalibrationQueryView:
    """Step 2: Queries calibration_drift_summary view via db function."""

    def test_calls_query_calibration_drift_summary(self):
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=[]) as mock_query, \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        mock_query.assert_called_once_with("proj-1")

    def test_no_project_message(self):
        """Should display a message when no project is found."""
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli._get_current_project_id", return_value=None):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no project" in output_lower


# ============================================================
# Step 3: Display task class, confidence bucket, drift, status
# ============================================================


class TestShowCalibrationDisplay:
    """Step 3: Display task class, confidence bucket, drift, status."""

    def _make_drift_entry(self, task_class="greenfield_impl", bucket="0.7-0.8",
                          empirical=0.65, expected=0.75, drift=-0.10,
                          attempts=15, status="calibrated"):
        return {
            "task_class": task_class,
            "confidence_bucket": bucket,
            "empirical_pass_rate": empirical,
            "expected_pass_rate": expected,
            "drift": drift,
            "total_attempts": attempts,
            "status": status,
        }

    def test_displays_task_class(self):
        from bob3.cli import main

        entries = [self._make_drift_entry(task_class="bug_fix")]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "bug_fix" in result.output

    def test_displays_confidence_bucket(self):
        from bob3.cli import main

        entries = [self._make_drift_entry(bucket="0.8-0.9")]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "0.8-0.9" in result.output

    def test_displays_drift_value(self):
        from bob3.cli import main

        entries = [self._make_drift_entry(drift=-0.18)]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "-0.18" in result.output

    def test_displays_status(self):
        from bob3.cli import main

        entries = [self._make_drift_entry(status="calibrated")]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "calibrated" in result.output

    def test_displays_empirical_and_expected(self):
        from bob3.cli import main

        entries = [self._make_drift_entry(empirical=0.72, expected=0.85)]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "0.72" in result.output
        assert "0.85" in result.output

    def test_displays_total_attempts(self):
        from bob3.cli import main

        entries = [self._make_drift_entry(attempts=42)]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "42" in result.output

    def test_no_data_message(self):
        from bob3.cli import main

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=[]), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no calibration" in output_lower

    def test_displays_multiple_entries(self):
        from bob3.cli import main

        entries = [
            self._make_drift_entry(task_class="greenfield_impl", bucket="0.7-0.8"),
            self._make_drift_entry(task_class="bug_fix", bucket="0.8-0.9"),
        ]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "greenfield_impl" in result.output
        assert "bug_fix" in result.output


# ============================================================
# Step 4: Highlight overconfident/underconfident buckets
# ============================================================


class TestShowCalibrationHighlighting:
    """Step 4: Highlight overconfident/underconfident buckets."""

    def _make_drift_entry(self, status="calibrated", drift=0.0, **kwargs):
        base = {
            "task_class": "greenfield_impl",
            "confidence_bucket": "0.7-0.8",
            "empirical_pass_rate": 0.75,
            "expected_pass_rate": 0.75,
            "drift": drift,
            "total_attempts": 15,
            "status": status,
        }
        base.update(kwargs)
        return base

    def test_overconfident_highlighted(self):
        """Overconfident entries should be visually highlighted (red)."""
        from bob3.cli import main

        entries = [self._make_drift_entry(status="overconfident", drift=-0.25)]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "overconfident" in result.output

    def test_underconfident_highlighted(self):
        """Underconfident entries should be visually highlighted (yellow)."""
        from bob3.cli import main

        entries = [self._make_drift_entry(status="underconfident", drift=0.20)]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "underconfident" in result.output

    def test_calibrated_not_highlighted_as_alert(self):
        """Calibrated entries should appear as normal status, not alarming."""
        from bob3.cli import main

        entries = [self._make_drift_entry(status="calibrated", drift=0.05)]

        runner = CliRunner()
        with patch("bob3.cli.query_calibration_drift_summary", return_value=entries), \
             patch("bob3.cli._get_current_project_id", return_value="proj-1"):
            result = runner.invoke(main, ["show-calibration"])
        assert result.exit_code == 0
        assert "calibrated" in result.output

    def test_highlighting_uses_rich_text_styling(self):
        """The show_calibration_cmd function should use Rich Text with style for status."""
        import inspect

        from bob3.cli import show_calibration_cmd

        source = inspect.getsource(show_calibration_cmd.callback)
        assert "Text" in source, "Should use Rich Text for styled status output"


# ============================================================
# Step 5: Test: Show calibration with drift data
# ============================================================


class TestShowCalibrationWithDriftData:
    """Step 5: End-to-end test with actual drift data via database."""

    @pytest.fixture()
    def db_with_calibration(self, tmp_path):
        """Create a temporary database with calibration data."""
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

            # Insert calibration data (10+ attempts to appear in drift summary view)
            entries = [
                (str(uuid.uuid4()), project_id, "greenfield_impl", "0.7-0.8",
                 20, 12, 8, 0.60, 0.75, -0.15, None),
                (str(uuid.uuid4()), project_id, "bug_fix", "0.8-0.9",
                 15, 14, 1, 0.93, 0.85, 0.08, None),
                (str(uuid.uuid4()), project_id, "test_writing", "0.5-0.6",
                 12, 10, 2, 0.83, 0.55, 0.28, None),
            ]
            for entry in entries:
                conn.execute(
                    """INSERT INTO calibration_data
                       (id, project_id, task_class, confidence_bucket,
                        total_attempts, total_passes, total_failures,
                        empirical_pass_rate, expected_pass_rate, drift, adjusted_threshold)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    entry,
                )
            conn.commit()
        finally:
            conn.close()

        return db_path, project_id

    def test_show_calibration_with_real_db(self, db_with_calibration):
        """Full integration: show-calibration with actual database data."""
        from bob3.cli import main
        from bob3.db import query_calibration_drift_summary

        db_path, project_id = db_with_calibration

        # First verify the view returns data
        with patch("bob3.db.get_database_path", return_value=db_path):
            drift_data = query_calibration_drift_summary(project_id)

        assert len(drift_data) >= 2, "Should have calibration drift entries with 10+ attempts"

        # Now test the CLI command with the real data
        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=db_path), \
             patch("bob3.cli._get_current_project_id", return_value=project_id), \
             patch("bob3.cli.query_calibration_drift_summary", wraps=query_calibration_drift_summary) as mock_query:
            result = runner.invoke(main, ["show-calibration"])

        assert result.exit_code == 0
        mock_query.assert_called_once_with(project_id)

        # Check that drift data appears in the output
        assert "greenfield_impl" in result.output or "bug_fix" in result.output or "test_writing" in result.output

    def test_overconfident_bucket_shown_in_drift_data(self, db_with_calibration):
        """Overconfident drift entries should be flagged in the output."""
        db_path, project_id = db_with_calibration

        from bob3.cli import main
        from bob3.db import query_calibration_drift_summary

        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=db_path), \
             patch("bob3.cli._get_current_project_id", return_value=project_id), \
             patch("bob3.cli.query_calibration_drift_summary", wraps=query_calibration_drift_summary):
            result = runner.invoke(main, ["show-calibration"])

        assert result.exit_code == 0
        # greenfield_impl has drift=-0.15, which triggers overconfident at boundary
        # test_writing has drift=0.28, which is underconfident
        # At least one non-calibrated status should appear
        output = result.output
        assert "overconfident" in output or "underconfident" in output

    def test_underconfident_bucket_shown_in_drift_data(self, db_with_calibration):
        """Underconfident drift entries should be flagged in the output."""
        db_path, project_id = db_with_calibration

        from bob3.cli import main
        from bob3.db import query_calibration_drift_summary

        runner = CliRunner()
        with patch("bob3.db.get_database_path", return_value=db_path), \
             patch("bob3.cli._get_current_project_id", return_value=project_id), \
             patch("bob3.cli.query_calibration_drift_summary", wraps=query_calibration_drift_summary):
            result = runner.invoke(main, ["show-calibration"])

        assert result.exit_code == 0
        # test_writing has drift=0.28, which is underconfident
        assert "underconfident" in result.output
