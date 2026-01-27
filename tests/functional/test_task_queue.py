"""Functional tests for task queue operations."""
import pytest
from pathlib import Path
from bob.database.manager import DatabaseManager
from bob.orchestrator.task_queue import TaskQueue
from bob.models.base import Task, TaskStatus, Project


class TestTaskQueueFunctional:
    """Test task queue operations work correctly."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Set up database and task queue."""
        db = DatabaseManager(tmp_path / "test.db")
        project = Project(
            id="test-proj-queue",
            name="test-project",
            description="Test project for queue",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        queue = TaskQueue(db, project_id)
        return db, project_id, queue

    def test_get_ready_tasks_returns_pending(self, setup):
        """Test get_ready_tasks returns tasks that are ready to run."""
        db, project_id, queue = setup
        
        # Create a task with no dependencies
        task = Task(
            id="task-ready-001",
            project_id=project_id,
            spec_id="F001",
            title="Ready Task",
            description="A ready task",
            status=TaskStatus.PENDING,
        )
        db.create_task(task)
        
        ready = queue.get_ready_tasks()
        assert len(ready) >= 1
        assert any(t.spec_id == "F001" for t in ready)

    def test_blocked_tasks_not_ready(self, setup):
        """Test tasks with incomplete dependencies are not ready."""
        db, project_id, queue = setup
        
        # Create blocking task (not completed)
        blocker = Task(
            id="task-blocker-001",
            project_id=project_id,
            spec_id="F001",
            title="Blocker",
            description="Blocking task",
            status=TaskStatus.PENDING,
        )
        db.create_task(blocker)
        
        # Create blocked task
        blocked = Task(
            id="task-blocked-001",
            project_id=project_id,
            spec_id="F002",
            title="Blocked",
            description="Blocked task",
            depends_on=["F001"],
            status=TaskStatus.PENDING,
        )
        db.create_task(blocked)
        
        ready = queue.get_ready_tasks()
        # F002 should not be ready because F001 is not completed
        assert not any(t.spec_id == "F002" for t in ready)

    def test_task_becomes_ready_after_dependency_completes(self, setup):
        """Test tasks become ready when dependencies complete."""
        db, project_id, queue = setup
        
        # Create and complete blocker
        blocker = Task(
            id="task-complete-blocker",
            project_id=project_id,
            spec_id="F001",
            title="Blocker",
            description="Blocking task",
            status=TaskStatus.PENDING,
        )
        blocker_id = db.create_task(blocker)
        db.update_task(blocker_id, status=TaskStatus.COMPLETED)
        
        # Create dependent task
        dependent = Task(
            id="task-dependent-001",
            project_id=project_id,
            spec_id="F002",
            title="Dependent",
            description="Dependent task",
            depends_on=["F001"],
            status=TaskStatus.PENDING,
        )
        db.create_task(dependent)
        
        ready = queue.get_ready_tasks()
        # F002 should now be ready
        assert any(t.spec_id == "F002" for t in ready)
