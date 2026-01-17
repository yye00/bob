"""Tests for bob.cli.run module (run commands for agent execution)."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import AgentType, Project, ProjectStatus, Session, SessionStatus, Task, TaskStatus


def extract_json(output: str) -> dict:
    """Extract JSON from output that may contain extra text (e.g., stderr messages).

    Args:
        output: Output string that contains JSON, possibly with extra text

    Returns:
        Parsed JSON object
    """
    # Try to parse the whole output first
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # If that fails, try to extract just the JSON part
        # Look for lines starting with { or [
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        # If we still can't find it, try to find JSON in the middle
        start = output.find('{')
        if start == -1:
            start = output.find('[')
        if start != -1:
            # Find the matching closing brace/bracket
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(output)):
                c = output[i]
                if escape:
                    escape = False
                    continue
                if c == '\\':
                    escape = True
                    continue
                if c == '"' and not escape:
                    in_string = not in_string
                if not in_string:
                    if c in '{[':
                        depth += 1
                    elif c in '}]':
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(output[start:i+1])
                            except json.JSONDecodeError:
                                pass
        raise ValueError(f"Could not extract JSON from output: {output}")


class TestRunCommand:
    """Test run command basic functionality."""

    def test_run_help(self) -> None:
        """Test run command help text."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])

        assert result.exit_code == 0
        assert "Run the autonomous coding agent" in result.output
        assert "--parallel" in result.output
        assert "--task" in result.output
        assert "--max-turns" in result.output

    def test_run_no_active_project(self, tmp_path: Path) -> None:
        """Test run command fails when no active project exists."""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        result = runner.invoke(cli, ["--db", str(db_path), "run"])

        assert result.exit_code == 1
        assert "No active project found" in result.output

    def test_run_no_active_project_json(self, tmp_path: Path) -> None:
        """Test run command fails with JSON output when no active project."""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        result = runner.invoke(cli, ["--db", str(db_path), "run", "--json"])

        assert result.exit_code == 1
        output = extract_json(result.output)
        assert output["error"] == "No active project found"


class TestRunParallelExecution:
    """Test run command with --parallel flag."""

    @pytest.fixture
    def setup_project_with_tasks(self, tmp_path: Path):
        """Setup a test project with multiple independent tasks."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create project
        project = Project(
            id="proj-001",
            name="test-parallel",
            description="Test parallel execution",
            workspace_dir=str(tmp_path / "workspace"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create 5 independent tasks (no dependencies)
        tasks = []
        for i in range(1, 6):
            task = Task(
                id=f"task-{i:03d}",
                project_id=project.id,
                spec_id=f"F{i:03d}",
                title=f"Test Task {i}",
                description=f"Description for task {i}",
                status=TaskStatus.PENDING,
                priority="medium",
                category="functional",
                depends_on=[],  # No dependencies
                attempts=0,
            )
            db.create_task(task)
            tasks.append(task)

        return db_path, project, tasks

    def test_run_parallel_basic(self, setup_project_with_tasks) -> None:
        """Test basic parallel execution with --parallel flag."""
        db_path, project, tasks = setup_project_with_tasks
        runner = CliRunner()

        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
        ])

        assert result.exit_code == 0
        assert "Running 3 tasks in parallel" in result.output
        assert "Parallel execution completed" in result.output

    def test_run_parallel_displays_task_table(self, setup_project_with_tasks) -> None:
        """Test that parallel execution displays task table."""
        db_path, project, tasks = setup_project_with_tasks
        runner = CliRunner()

        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
        ])

        assert result.exit_code == 0
        # Check that task IDs appear in output
        assert "F001" in result.output
        assert "F002" in result.output
        assert "F003" in result.output

    def test_run_parallel_json_output(self, setup_project_with_tasks) -> None:
        """Test parallel execution with JSON output."""
        db_path, project, tasks = setup_project_with_tasks
        runner = CliRunner()

        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        assert output["status"] == "completed"
        assert output["tasks_run"] == 3
        assert output["max_workers"] == 3
        assert len(output["results"]) == 3

        # Verify each result has required fields
        for res in output["results"]:
            assert "task_id" in res
            assert "spec_id" in res
            assert "session_id" in res
            assert "status" in res
            assert "started_at" in res
            assert "completed_at" in res

    def test_run_parallel_respects_max_workers(self, setup_project_with_tasks) -> None:
        """Test that parallel execution respects max_workers limit."""
        db_path, project, tasks = setup_project_with_tasks
        runner = CliRunner()

        # Run with max_workers=2, should only run 2 tasks
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "2",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        assert output["tasks_run"] == 2
        assert len(output["results"]) == 2

    def test_run_parallel_creates_sessions(self, setup_project_with_tasks) -> None:
        """Test that parallel execution creates separate sessions for each task."""
        db_path, project, tasks = setup_project_with_tasks
        runner = CliRunner()

        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)

        # Verify that each task got a unique session ID
        session_ids = [res["session_id"] for res in output["results"]]
        assert len(session_ids) == len(set(session_ids))  # All unique

        # Verify sessions exist in database
        db = DatabaseManager(db_path)
        all_sessions = db.list_sessions(project_id=project.id)

        # Verify all session IDs from results exist in database
        db_session_ids = {s.id for s in all_sessions}
        for session_id in session_ids:
            assert session_id in db_session_ids

    def test_run_parallel_no_ready_tasks(self, tmp_path: Path) -> None:
        """Test parallel execution when no tasks are ready."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create project with no tasks
        project = Project(
            id="proj-001",
            name="test-empty",
            description="Test with no tasks",
            workspace_dir=str(tmp_path / "workspace"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
        ])

        assert result.exit_code == 0
        assert "No tasks ready to execute" in result.output

    def test_run_parallel_no_ready_tasks_json(self, tmp_path: Path) -> None:
        """Test parallel execution JSON output when no tasks are ready."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create project with no tasks
        project = Project(
            id="proj-001",
            name="test-empty",
            description="Test with no tasks",
            workspace_dir=str(tmp_path / "workspace"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        assert output["status"] == "no_tasks"
        assert "No tasks ready to execute" in output["message"]

    def test_run_parallel_with_blocked_tasks(self, tmp_path: Path) -> None:
        """Test parallel execution skips blocked tasks."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create project
        project = Project(
            id="proj-001",
            name="test-blocked",
            description="Test with blocked tasks",
            workspace_dir=str(tmp_path / "workspace"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create task F001 (PENDING, no dependencies - ready)
        task1 = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Task 1",
            description="Independent task",
            status=TaskStatus.PENDING,
            priority="high",
            category="functional",
            depends_on=[],
            attempts=0,
        )
        db.create_task(task1)

        # Create task F002 (PENDING, depends on F001 - blocked)
        task2 = Task(
            id="task-002",
            project_id=project.id,
            spec_id="F002",
            title="Task 2",
            description="Blocked task",
            status=TaskStatus.PENDING,
            priority="high",
            category="functional",
            depends_on=["F001"],  # Blocked by F001
            attempts=0,
        )
        db.create_task(task2)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "2",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        # Should only run 1 task (F001), F002 is blocked
        assert output["tasks_run"] == 1
        assert output["results"][0]["spec_id"] == "F001"

    def test_run_parallel_prioritizes_critical_tasks(self, tmp_path: Path) -> None:
        """Test that parallel execution prioritizes critical/high priority tasks."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create project
        project = Project(
            id="proj-001",
            name="test-priority",
            description="Test priority handling",
            workspace_dir=str(tmp_path / "workspace"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create tasks with different priorities
        priorities = [("F001", "low"), ("F002", "critical"), ("F003", "medium"), ("F004", "high")]
        for spec_id, priority in priorities:
            task = Task(
                id=f"task-{spec_id}",
                project_id=project.id,
                spec_id=spec_id,
                title=f"Task {spec_id}",
                description=f"{priority} priority task",
                status=TaskStatus.PENDING,
                priority=priority,
                category="functional",
                depends_on=[],
                attempts=0,
            )
            db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "2",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        assert output["tasks_run"] == 2

        # Should run critical and high priority first
        spec_ids = [res["spec_id"] for res in output["results"]]
        assert "F002" in spec_ids  # critical
        assert "F004" in spec_ids  # high


class TestRunCommandOptions:
    """Test run command with various options."""

    def test_run_with_max_turns_option(self, tmp_path: Path) -> None:
        """Test run command accepts --max-turns option."""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        # Should parse without error (will fail on no project, but validates options)
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--max-turns", "50",
        ])

        # Validates that option is accepted
        assert "--max-turns" not in result.output or "Error" not in result.output

    def test_run_with_agent_option(self, tmp_path: Path) -> None:
        """Test run command accepts --agent option."""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        # Should parse without error
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--agent", "coding",
        ])

        # Validates that option is accepted
        assert "--agent" not in result.output or "Error" not in result.output

    def test_run_with_model_option(self, tmp_path: Path) -> None:
        """Test run command accepts --model option."""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        # Should parse without error
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--model", "opus",
        ])

        # Validates that option is accepted
        assert "--model" not in result.output or "Error" not in result.output

    def test_run_with_task_option_implemented(self, tmp_path: Path) -> None:
        """Test that --task option works with orchestrator."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create workspace dir
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create project
        project = Project(
            id="proj-001",
            name="test-task",
            description="Test task option",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create a task
        task = Task(
            id="task-001",
            project_id="proj-001",
            spec_id="F001",
            title="Test Task",
            description="Test task description",
            status=TaskStatus.PENDING,
            priority="high",
            category="functional",
            depends_on=[],
            attempts=0,
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--task", "F001",
            "--json",
        ])

        assert result.exit_code == 0
        output = extract_json(result.output)
        assert output["status"] == "completed"
        assert output["task_id"] == "F001"

    def test_run_without_options_auto_select(self, tmp_path: Path) -> None:
        """Test that run without --task auto-selects the next ready task."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create workspace dir
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create project
        project = Project(
            id="proj-001",
            name="test-auto",
            description="Test auto-select",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create multiple tasks with different priorities
        for spec_id, priority in [("F001", "low"), ("F002", "critical"), ("F003", "high")]:
            task = Task(
                id=f"task-{spec_id}",
                project_id="proj-001",
                spec_id=spec_id,
                title=f"Task {spec_id}",
                description=f"{priority} priority task",
                status=TaskStatus.PENDING,
                priority=priority,
                category="functional",
                depends_on=[],
                attempts=0,
            )
            db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--json",
        ])

        assert result.exit_code == 0
        output = extract_json(result.output)
        assert output["status"] == "completed"
        # Should auto-select the highest priority task (critical)
        assert output["task_id"] == "F002"
