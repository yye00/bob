"""Tests for bob metrics CLI command."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.observability.telemetry import RunTelemetry


@pytest.fixture
def runner():
    return CliRunner()


def _parse_json_output(output: str) -> dict:
    """Parse JSON from CLI output, handling extra lines from DB migration messages."""
    # The output may contain extra lines like "✓ Applied schema version 6"
    # Try to parse the first valid JSON object/array
    lines = output.strip().split('\n')
    
    # Try parsing from the first line, accumulating lines until valid JSON
    for start in range(len(lines)):
        for end in range(start + 1, len(lines) + 1):
            candidate = '\n'.join(lines[start:end])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    
    raise ValueError(f"No valid JSON found in output: {output!r}")


class TestMetricsCommand:
    """Test the metrics CLI command."""

    def test_metrics_no_project(self, runner, tmp_path):
        """Test metrics with no active project."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(cli, ["--db", str(db_path), "metrics", "--json"])
        assert result.exit_code == 0
        data = _parse_json_output(result.output)
        assert "error" in data

    def test_metrics_no_telemetry(self, runner, tmp_path):
        """Test metrics with a project but no telemetry."""
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus

        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-1",
            name="test",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        result = runner.invoke(cli, ["--db", str(db_path), "metrics", "--json"])
        assert result.exit_code == 0
        data = _parse_json_output(result.output)
        assert "error" in data
        assert "No telemetry" in data["error"]

    def test_metrics_last_run_json(self, runner, tmp_path):
        """Test metrics JSON output for last run."""
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus

        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-1",
            name="test",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create telemetry data
        rt = RunTelemetry(workspace=workspace, run_id="test-run-001")
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Feature 1", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=True)
        rt.set_task_final_status("t1", "completed")
        rt.end_run()

        result = runner.invoke(cli, ["--db", str(db_path), "metrics", "--json"])
        assert result.exit_code == 0
        data = _parse_json_output(result.output)
        assert data["run_id"] == "test-run-001"
        assert data["tasks_completed"] == 1

    def test_metrics_specific_run(self, runner, tmp_path):
        """Test metrics for a specific run ID."""
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus

        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-1",
            name="test",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create two runs
        rt1 = RunTelemetry(workspace=workspace, run_id="run-alpha")
        rt1.start_run()
        rt1.end_run()

        rt2 = RunTelemetry(workspace=workspace, run_id="run-beta")
        rt2.start_run()
        rt2.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt2.end_task_attempt(task_id="t1", success=True)
        rt2.end_run()

        result = runner.invoke(cli, ["--db", str(db_path), "metrics", "--run", "run-alpha", "--json"])
        assert result.exit_code == 0
        data = _parse_json_output(result.output)
        assert data["run_id"] == "run-alpha"

    def test_metrics_task_history(self, runner, tmp_path):
        """Test metrics for a specific task across runs."""
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus

        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-1",
            name="test",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create a run with a known task
        rt = RunTelemetry(workspace=workspace, run_id="run-abc")
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test Task", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=True)
        rt.set_task_final_status("t1", "completed")
        rt.end_run()

        result = runner.invoke(cli, ["--db", str(db_path), "metrics", "--task", "F001", "--json"])
        assert result.exit_code == 0
        data = _parse_json_output(result.output)
        assert data["task_id"] == "F001"
        assert len(data["runs"]) == 1
        assert data["runs"][0]["spec_id"] == "F001"

    def test_metrics_task_not_found(self, runner, tmp_path):
        """Test metrics for a task that doesn't exist."""
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus

        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-1",
            name="test",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create a run with no matching task
        rt = RunTelemetry(workspace=workspace, run_id="run-xyz")
        rt.start_run()
        rt.end_run()

        result = runner.invoke(cli, ["--db", str(db_path), "metrics", "--task", "NONEXISTENT", "--json"])
        assert result.exit_code == 0
        data = _parse_json_output(result.output)
        assert "error" in data

    def test_metrics_rich_output(self, runner, tmp_path):
        """Test metrics with Rich table output (non-JSON)."""
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus

        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-1",
            name="test",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        rt = RunTelemetry(workspace=workspace, run_id="run-rich")
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=True)
        rt.set_task_final_status("t1", "completed")
        rt.end_run()

        result = runner.invoke(cli, ["--db", str(db_path), "metrics"])
        assert result.exit_code == 0
        assert "run-rich" in result.output
