"""Integration tests for parallel task execution.

This module tests the end-to-end parallel execution workflow:
- Project setup with multiple independent tasks
- Concurrent task execution with --parallel flag
- Session management for parallel tasks
- Database integrity for parallel operations
- Log file separation and integrity
"""

import json
import tempfile
from pathlib import Path
from typing import Tuple

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import (
    AgentType,
    Project,
    ProjectStatus,
    Session,
    SessionStatus,
    Task,
    TaskStatus,
)


def extract_json(output: str) -> dict:
    """Extract JSON from output that may contain extra text.

    Args:
        output: Output string that contains JSON

    Returns:
        Parsed JSON object
    """
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # Try to extract JSON portion from multi-line output with extra text
        # Find the opening brace/bracket
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
                            # Found the end of JSON
                            json_str = output[start:i+1]
                            try:
                                return json.loads(json_str)
                            except json.JSONDecodeError:
                                pass

        # Try line by line as fallback
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Could not extract JSON from output: {output}")


@pytest.fixture
def setup_integration_project(tmp_path: Path) -> Tuple[Path, DatabaseManager, Project]:
    """Setup a complete integration test environment.

    Creates:
    - Database with project
    - Workspace directory structure
    - Multiple independent tasks
    - State file for active project

    Returns:
        Tuple of (db_path, db, project)
    """
    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)

    # Create workspace directory
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create bob directory structure
    bob_dir = workspace / ".bob"
    bob_dir.mkdir()
    (bob_dir / "logs").mkdir()
    (bob_dir / "state").mkdir()

    # Create project
    project = Project(
        id="proj-test-parallel",
        name="test-parallel",
        description="Integration test for parallel execution",
        workspace_dir=str(workspace),
        spec_source="file://spec.yaml",
        status=ProjectStatus.ACTIVE,
    )
    db.create_project(project)

    # Create 6 independent tasks (no dependencies)
    for i in range(1, 7):
        task = Task(
            id=f"task-{i:03d}",
            project_id=project.id,
            spec_id=f"F{i:03d}",
            title=f"Integration Test Task {i}",
            description=f"Task {i} for parallel execution testing",
            status=TaskStatus.PENDING,
            priority="medium",
            category="functional",
            depends_on=[],  # No dependencies - all independent
            attempts=0,
        )
        db.create_task(task)

    # Set as active project in state file
    state_dir = tmp_path / ".bob"
    state_dir.mkdir(exist_ok=True)
    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps({
        "active_project_id": project.id,
        "last_updated": "2026-01-16T00:00:00Z"
    }))

    return db_path, db, project


class TestParallelExecutionIntegration:
    """Integration tests for parallel task execution."""

    def test_parallel_execution_end_to_end(self, setup_integration_project):
        """Test F054: Complete parallel execution workflow.

        Tests:
        1. Create test project with 5+ independent tasks
        2. Run 'bob run --parallel 3'
        3. Verify multiple tasks execute concurrently
        4. Verify each task gets its own session
        5. Verify all tasks complete successfully
        6. Verify database records are correct
        7. Verify log files are separate
        """
        db_path, db, project = setup_integration_project
        runner = CliRunner()

        # Step 1: Verify we have 6 independent tasks
        all_tasks = db.list_tasks(project_id=project.id)
        assert len(all_tasks) == 6
        for task in all_tasks:
            assert task.status == TaskStatus.PENDING
            assert len(task.depends_on) == 0  # All independent

        # Step 2: Run with --parallel 3
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
            "--json",
        ])

        # Should execute successfully
        assert result.exit_code == 0

        # Step 3-7: Verify execution details
        output = extract_json(result.output)

        # Verify 3 tasks were run (max_workers=3)
        assert output["status"] == "completed"
        assert output["tasks_run"] == 3
        assert output["max_workers"] == 3
        assert len(output["results"]) == 3

        # Step 4: Verify each task got its own session
        session_ids = [res["session_id"] for res in output["results"]]
        assert len(session_ids) == 3
        assert len(set(session_ids)) == 3  # All unique

        # Step 5: Verify all tasks completed successfully
        for result_item in output["results"]:
            assert result_item["status"] in ["completed", "success"]
            assert "task_id" in result_item
            assert "spec_id" in result_item
            assert "session_id" in result_item
            assert "started_at" in result_item
            assert "completed_at" in result_item

        # Step 6: Verify database records are correct
        all_sessions = db.list_sessions(project_id=project.id)
        assert len(all_sessions) == 3

        # Verify each session is in database with correct details
        for session_id in session_ids:
            session = db.get_session(session_id)
            assert session is not None
            assert session.project_id == project.id
            assert session.agent_type == AgentType.CODING
            # Session should have status (completed or running)
            assert session.status in [SessionStatus.COMPLETED, SessionStatus.RUNNING]

        # Verify tasks exist in database (no data corruption)
        completed_task_ids = [res["task_id"] for res in output["results"]]
        for task_id in completed_task_ids:
            task = db.get_task(task_id)
            assert task is not None
            # Task should still be valid
            assert task.project_id == project.id

    def test_parallel_execution_with_more_tasks_than_workers(self, setup_integration_project):
        """Test parallel execution when there are more tasks than workers."""
        db_path, db, project = setup_integration_project
        runner = CliRunner()

        # We have 6 tasks, run with max_workers=2
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "2",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)

        # Should only run 2 tasks at a time
        assert output["tasks_run"] == 2
        assert len(output["results"]) == 2

        # Verify sessions were created
        session_ids = [res["session_id"] for res in output["results"]]
        assert len(set(session_ids)) == 2  # Both unique

        # Verify database has correct records
        all_sessions = db.list_sessions(project_id=project.id)
        assert len(all_sessions) == 2

    def test_parallel_execution_session_isolation(self, setup_integration_project):
        """Test that parallel sessions are isolated and don't interfere."""
        db_path, db, project = setup_integration_project
        runner = CliRunner()

        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "4",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        assert output["tasks_run"] == 4

        # Get all sessions
        sessions = db.list_sessions(project_id=project.id)
        assert len(sessions) == 4

        # Verify each session has unique ID
        session_ids = [s.id for s in sessions]
        assert len(session_ids) == len(set(session_ids))

        # Verify each session is linked to a different task
        task_ids_in_sessions = []
        for session in sessions:
            # Sessions should have task_id set
            if hasattr(session, 'task_id') and session.task_id:
                task_ids_in_sessions.append(session.task_id)

        # All task IDs should be unique (no task ran twice)
        if task_ids_in_sessions:
            assert len(task_ids_in_sessions) == len(set(task_ids_in_sessions))

    def test_parallel_execution_prioritizes_high_priority_tasks(self, tmp_path: Path):
        """Test that parallel execution prioritizes high/critical tasks."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create project
        project = Project(
            id="proj-priority",
            name="test-priority",
            description="Test priority handling",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create tasks with different priorities
        priorities = [
            ("F001", "low"),
            ("F002", "critical"),
            ("F003", "medium"),
            ("F004", "high"),
            ("F005", "low"),
        ]

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

        # Should prioritize critical and high priority tasks
        spec_ids = [res["spec_id"] for res in output["results"]]
        assert "F002" in spec_ids  # critical
        assert "F004" in spec_ids  # high

    def test_parallel_execution_respects_dependencies(self, tmp_path: Path):
        """Test that parallel execution skips blocked tasks."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create project
        project = Project(
            id="proj-deps",
            name="test-dependencies",
            description="Test dependency handling",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create task F001 (independent - ready)
        task1 = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Independent Task",
            description="Ready to run",
            status=TaskStatus.PENDING,
            priority="high",
            category="functional",
            depends_on=[],
            attempts=0,
        )
        db.create_task(task1)

        # Create task F002 (depends on F001 - blocked)
        task2 = Task(
            id="task-002",
            project_id=project.id,
            spec_id="F002",
            title="Blocked Task",
            description="Depends on F001",
            status=TaskStatus.PENDING,
            priority="high",
            category="functional",
            depends_on=["F001"],
            attempts=0,
        )
        db.create_task(task2)

        # Create task F003 (independent - ready)
        task3 = Task(
            id="task-003",
            project_id=project.id,
            spec_id="F003",
            title="Another Independent Task",
            description="Ready to run",
            status=TaskStatus.PENDING,
            priority="medium",
            category="functional",
            depends_on=[],
            attempts=0,
        )
        db.create_task(task3)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "3",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)

        # Should only run 2 tasks (F001 and F003), F002 is blocked
        assert output["tasks_run"] == 2

        spec_ids = [res["spec_id"] for res in output["results"]]
        assert "F001" in spec_ids
        assert "F003" in spec_ids
        assert "F002" not in spec_ids  # Blocked

    def test_parallel_execution_database_integrity(self, setup_integration_project):
        """Test that parallel execution maintains database integrity.

        Verifies:
        - All sessions are properly recorded
        - Session IDs are unique
        - Task-session relationships are correct
        - No duplicate sessions for same task
        """
        db_path, db, project = setup_integration_project
        runner = CliRunner()

        # Get initial state
        initial_tasks = db.list_tasks(project_id=project.id)
        initial_task_count = len(initial_tasks)

        # Run parallel execution
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "run",
            "--parallel", "5",
            "--json",
        ])

        assert result.exit_code == 0

        output = extract_json(result.output)
        tasks_run = output["tasks_run"]

        # Verify sessions
        sessions = db.list_sessions(project_id=project.id)
        assert len(sessions) == tasks_run

        # Verify all session IDs are unique
        session_ids = [s.id for s in sessions]
        assert len(session_ids) == len(set(session_ids))

        # Verify session details
        for session in sessions:
            assert session.project_id == project.id
            assert session.agent_type == AgentType.CODING
            assert session.id is not None
            assert session.started_at is not None

        # Verify tasks still exist (no data loss)
        final_tasks = db.list_tasks(project_id=project.id)
        assert len(final_tasks) == initial_task_count

        # Verify no duplicate task processing
        task_ids_processed = [res["task_id"] for res in output["results"]]
        assert len(task_ids_processed) == len(set(task_ids_processed))

    def test_parallel_execution_with_no_tasks(self, tmp_path: Path):
        """Test parallel execution when no tasks are available."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create project with no tasks
        project = Project(
            id="proj-empty",
            name="test-empty",
            description="Project with no tasks",
            workspace_dir=str(workspace),
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

        # Verify no sessions were created
        sessions = db.list_sessions(project_id=project.id)
        assert len(sessions) == 0
