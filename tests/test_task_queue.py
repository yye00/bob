"""Tests for TaskQueue - dependency-aware task queue.

Tests task queue operations including dependency resolution, priority sorting,
and blocked task detection.
"""

import tempfile
from pathlib import Path

import pytest

from bob.database import DatabaseManager
from bob.models.base import Project, ProjectStatus, Task, TaskStatus
from bob.orchestrator.task_queue import TaskQueue


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(db_path)
        yield manager


@pytest.fixture
def sample_project(db):
    """Create a sample project for testing."""
    project = Project(
        id="proj-test-001",
        name="test-project",
        description="Test project",
        workspace_dir="/tmp/test-workspace",
        spec_source="file://spec.yaml",
        status=ProjectStatus.ACTIVE,
    )
    db.create_project(project)
    return project


class TestTaskQueueInit:
    """Test TaskQueue initialization."""

    def test_init_with_db_manager(self, db):
        """Test initializing TaskQueue with DatabaseManager."""
        queue = TaskQueue(db)
        assert queue.db_manager == db
        assert queue.project_id is None

    def test_init_with_project_id(self, db, sample_project):
        """Test initializing TaskQueue with project ID."""
        queue = TaskQueue(db, project_id=sample_project.id)
        assert queue.db_manager == db
        assert queue.project_id == sample_project.id


class TestGetReadyTasks:
    """Test get_ready_tasks() method."""

    def test_get_ready_tasks_empty(self, db, sample_project):
        """Test get_ready_tasks with no tasks."""
        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()
        assert ready == []

    def test_get_ready_tasks_single_task_no_dependencies(self, db, sample_project):
        """Test get_ready_tasks with single task and no dependencies."""
        task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Task 1",
            description="First task",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].spec_id == "F001"

    def test_get_ready_tasks_multiple_tasks_no_dependencies(self, db, sample_project):
        """Test get_ready_tasks with multiple independent tasks."""
        tasks = [
            Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                priority=priority,
                depends_on=[],
            )
            for i, priority in enumerate(["low", "high", "critical", "medium"], 1)
        ]
        for task in tasks:
            db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()

        # Should return all tasks sorted by priority
        assert len(ready) == 4
        assert ready[0].spec_id == "F003"  # critical
        assert ready[1].spec_id == "F002"  # high
        assert ready[2].spec_id == "F004"  # medium
        assert ready[3].spec_id == "F001"  # low

    def test_get_ready_tasks_with_completed_dependency(self, db, sample_project):
        """Test task becomes ready when dependency is completed."""
        # Create dependency task (completed)
        dep_task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency task",
            status=TaskStatus.COMPLETED,
            depends_on=[],
        )
        db.create_task(dep_task)

        # Create dependent task (pending)
        task = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Dependent",
            description="Dependent task",
            status=TaskStatus.PENDING,
            depends_on=["F001"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()

        # Should return the dependent task since dependency is completed
        assert len(ready) == 1
        assert ready[0].spec_id == "F002"

    def test_get_ready_tasks_blocks_on_pending_dependency(self, db, sample_project):
        """Test task is blocked when dependency is pending."""
        # Create dependency task (pending)
        dep_task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency task",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(dep_task)

        # Create dependent task (pending)
        task = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Dependent",
            description="Dependent task",
            status=TaskStatus.PENDING,
            depends_on=["F001"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()

        # Should return only the dependency task, not the dependent
        assert len(ready) == 1
        assert ready[0].spec_id == "F001"

    def test_get_ready_tasks_blocks_on_failed_dependency(self, db, sample_project):
        """Test task is blocked when dependency failed."""
        # Create dependency task (failed)
        dep_task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency task",
            status=TaskStatus.FAILED,
            depends_on=[],
        )
        db.create_task(dep_task)

        # Create dependent task (pending)
        task = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Dependent",
            description="Dependent task",
            status=TaskStatus.PENDING,
            depends_on=["F001"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()

        # Should not return the dependent task since dependency failed
        assert len(ready) == 0

    def test_get_ready_tasks_complex_dependency_graph(self, db, sample_project):
        """Test with complex dependency graph (DAG)."""
        # Create a dependency graph:
        #   F001 (completed) -> F003 (pending)
        #   F002 (completed) -> F003 (pending)
        #   F003 (pending) -> F004 (pending)

        tasks = [
            Task(
                id="task-001",
                project_id=sample_project.id,
                spec_id="F001",
                title="Task 1",
                description="Task 1",
                status=TaskStatus.COMPLETED,
                depends_on=[],
            ),
            Task(
                id="task-002",
                project_id=sample_project.id,
                spec_id="F002",
                title="Task 2",
                description="Task 2",
                status=TaskStatus.COMPLETED,
                depends_on=[],
            ),
            Task(
                id="task-003",
                project_id=sample_project.id,
                spec_id="F003",
                title="Task 3",
                description="Task 3",
                status=TaskStatus.PENDING,
                depends_on=["F001", "F002"],
                priority="high",
            ),
            Task(
                id="task-004",
                project_id=sample_project.id,
                spec_id="F004",
                title="Task 4",
                description="Task 4",
                status=TaskStatus.PENDING,
                depends_on=["F003"],
                priority="critical",
            ),
        ]
        for task in tasks:
            db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()

        # Should return only F003 (both dependencies completed)
        # F004 is blocked by F003
        assert len(ready) == 1
        assert ready[0].spec_id == "F003"

    def test_get_ready_tasks_limit(self, db, sample_project):
        """Test get_ready_tasks respects limit parameter."""
        # Create 5 ready tasks
        for i in range(1, 6):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                depends_on=[],
            )
            db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)

        # Test limit=3
        ready = queue.get_ready_tasks(limit=3)
        assert len(ready) == 3

        # Test limit=10 (more than available)
        ready = queue.get_ready_tasks(limit=10)
        assert len(ready) == 5

    def test_get_ready_tasks_excludes_non_pending_status(self, db, sample_project):
        """Test get_ready_tasks only returns PENDING tasks."""
        statuses = [
            TaskStatus.PENDING,
            TaskStatus.IN_PROGRESS,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.BLOCKED,
            TaskStatus.DEPRECATED,
        ]

        for i, status in enumerate(statuses, 1):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=status,
                depends_on=[],
            )
            db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        ready = queue.get_ready_tasks()

        # Should only return the PENDING task
        assert len(ready) == 1
        assert ready[0].status == TaskStatus.PENDING


class TestGetBlockedTasks:
    """Test get_blocked_tasks() method."""

    def test_get_blocked_tasks_empty(self, db, sample_project):
        """Test get_blocked_tasks with no tasks."""
        queue = TaskQueue(db, project_id=sample_project.id)
        blocked = queue.get_blocked_tasks()
        assert blocked == []

    def test_get_blocked_tasks_single_blocked_task(self, db, sample_project):
        """Test get_blocked_tasks with single blocked task."""
        # Create dependency (pending)
        dep_task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency task",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(dep_task)

        # Create dependent task (blocked)
        task = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Dependent",
            description="Dependent task",
            status=TaskStatus.PENDING,
            depends_on=["F001"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        blocked = queue.get_blocked_tasks()

        assert len(blocked) == 1
        assert blocked[0][0].spec_id == "F002"
        assert blocked[0][1] == ["F001"]

    def test_get_blocked_tasks_multiple_blockers(self, db, sample_project):
        """Test task blocked by multiple dependencies."""
        # Create dependencies (both pending)
        for i in [1, 2]:
            dep_task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Dependency {i}",
                description=f"Dependency {i}",
                status=TaskStatus.PENDING,
                depends_on=[],
            )
            db.create_task(dep_task)

        # Create dependent task
        task = Task(
            id="task-003",
            project_id=sample_project.id,
            spec_id="F003",
            title="Dependent",
            description="Dependent task",
            status=TaskStatus.PENDING,
            depends_on=["F001", "F002"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        blocked = queue.get_blocked_tasks()

        assert len(blocked) == 1
        assert blocked[0][0].spec_id == "F003"
        assert set(blocked[0][1]) == {"F001", "F002"}

    def test_get_blocked_tasks_partial_blockers(self, db, sample_project):
        """Test task with some completed and some pending dependencies."""
        # Create dependencies (one completed, one pending)
        dep1 = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency 1",
            description="Completed dependency",
            status=TaskStatus.COMPLETED,
            depends_on=[],
        )
        db.create_task(dep1)

        dep2 = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Dependency 2",
            description="Pending dependency",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(dep2)

        # Create dependent task
        task = Task(
            id="task-003",
            project_id=sample_project.id,
            spec_id="F003",
            title="Dependent",
            description="Dependent task",
            status=TaskStatus.PENDING,
            depends_on=["F001", "F002"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        blocked = queue.get_blocked_tasks()

        # Should show only the pending blocker
        assert len(blocked) == 1
        assert blocked[0][0].spec_id == "F003"
        assert blocked[0][1] == ["F002"]

    def test_get_blocked_tasks_sorted_by_priority(self, db, sample_project):
        """Test blocked tasks are sorted by priority."""
        # Create dependency (pending)
        dep = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(dep)

        # Create blocked tasks with different priorities
        priorities = ["low", "critical", "medium", "high"]
        for i, priority in enumerate(priorities, 2):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                priority=priority,
                depends_on=["F001"],
            )
            db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        blocked = queue.get_blocked_tasks()

        # Should be sorted: critical, high, medium, low
        assert len(blocked) == 4
        assert blocked[0][0].spec_id == "F003"  # critical
        assert blocked[1][0].spec_id == "F005"  # high
        assert blocked[2][0].spec_id == "F004"  # medium
        assert blocked[3][0].spec_id == "F002"  # low


class TestGetTaskDependencyChain:
    """Test get_task_dependency_chain() method."""

    def test_dependency_chain_no_dependencies(self, db, sample_project):
        """Test dependency chain for task with no dependencies."""
        task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Task 1",
            description="Task 1",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        chain = queue.get_task_dependency_chain(task)

        assert chain == []

    def test_dependency_chain_single_dependency(self, db, sample_project):
        """Test dependency chain with single dependency."""
        # Create dependency
        dep = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency",
            status=TaskStatus.COMPLETED,
            depends_on=[],
        )
        db.create_task(dep)

        # Create dependent task
        task = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Task 2",
            description="Task 2",
            status=TaskStatus.PENDING,
            depends_on=["F001"],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        chain = queue.get_task_dependency_chain(task)

        assert len(chain) == 1
        assert chain[0].spec_id == "F001"

    def test_dependency_chain_nested_dependencies(self, db, sample_project):
        """Test dependency chain with nested dependencies."""
        # Create chain: F001 -> F002 -> F003
        tasks = [
            Task(
                id="task-001",
                project_id=sample_project.id,
                spec_id="F001",
                title="Task 1",
                description="Task 1",
                status=TaskStatus.COMPLETED,
                depends_on=[],
            ),
            Task(
                id="task-002",
                project_id=sample_project.id,
                spec_id="F002",
                title="Task 2",
                description="Task 2",
                status=TaskStatus.COMPLETED,
                depends_on=["F001"],
            ),
            Task(
                id="task-003",
                project_id=sample_project.id,
                spec_id="F003",
                title="Task 3",
                description="Task 3",
                status=TaskStatus.PENDING,
                depends_on=["F002"],
            ),
        ]
        for t in tasks:
            db.create_task(t)

        queue = TaskQueue(db, project_id=sample_project.id)
        chain = queue.get_task_dependency_chain(tasks[2])

        # Should return F001 and F002 in that order
        assert len(chain) == 2
        assert chain[0].spec_id == "F001"
        assert chain[1].spec_id == "F002"

    def test_dependency_chain_diamond_dependencies(self, db, sample_project):
        """Test dependency chain with diamond pattern."""
        # Create diamond:
        #     F001
        #    /    \
        #  F002  F003
        #    \    /
        #     F004
        tasks = [
            Task(
                id="task-001",
                project_id=sample_project.id,
                spec_id="F001",
                title="Task 1",
                description="Task 1",
                status=TaskStatus.COMPLETED,
                depends_on=[],
            ),
            Task(
                id="task-002",
                project_id=sample_project.id,
                spec_id="F002",
                title="Task 2",
                description="Task 2",
                status=TaskStatus.COMPLETED,
                depends_on=["F001"],
            ),
            Task(
                id="task-003",
                project_id=sample_project.id,
                spec_id="F003",
                title="Task 3",
                description="Task 3",
                status=TaskStatus.COMPLETED,
                depends_on=["F001"],
            ),
            Task(
                id="task-004",
                project_id=sample_project.id,
                spec_id="F004",
                title="Task 4",
                description="Task 4",
                status=TaskStatus.PENDING,
                depends_on=["F002", "F003"],
            ),
        ]
        for t in tasks:
            db.create_task(t)

        queue = TaskQueue(db, project_id=sample_project.id)
        chain = queue.get_task_dependency_chain(tasks[3])

        # Should return all dependencies
        spec_ids = {t.spec_id for t in chain}
        assert spec_ids == {"F001", "F002", "F003"}


class TestGetNextTask:
    """Test get_next_task() convenience method."""

    def test_get_next_task_returns_highest_priority(self, db, sample_project):
        """Test get_next_task returns highest priority ready task."""
        # Create tasks with different priorities
        for i, priority in enumerate(["low", "medium", "high", "critical"], 1):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                priority=priority,
                depends_on=[],
            )
            db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        next_task = queue.get_next_task()

        assert next_task is not None
        assert next_task.spec_id == "F004"  # critical priority

    def test_get_next_task_returns_none_when_empty(self, db, sample_project):
        """Test get_next_task returns None when no tasks ready."""
        queue = TaskQueue(db, project_id=sample_project.id)
        next_task = queue.get_next_task()
        assert next_task is None

    def test_get_next_task_skips_blocked_tasks(self, db, sample_project):
        """Test get_next_task skips blocked tasks."""
        # Create dependency (pending)
        dep = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Dependency",
            description="Dependency",
            status=TaskStatus.PENDING,
            priority="low",
            depends_on=[],
        )
        db.create_task(dep)

        # Create blocked task with higher priority
        blocked = Task(
            id="task-002",
            project_id=sample_project.id,
            spec_id="F002",
            title="Blocked",
            description="Blocked task",
            status=TaskStatus.PENDING,
            priority="critical",
            depends_on=["F001"],
        )
        db.create_task(blocked)

        queue = TaskQueue(db, project_id=sample_project.id)
        next_task = queue.get_next_task()

        # Should return F001 (the only ready task), not F002 (blocked)
        assert next_task is not None
        assert next_task.spec_id == "F001"


class TestRunParallel:
    """Test run_parallel() method for concurrent task execution."""

    def test_run_parallel_empty_list(self, db, sample_project):
        """Test run_parallel with empty task list."""
        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel([])
        assert results == []

    def test_run_parallel_single_task(self, db, sample_project):
        """Test run_parallel with single task."""
        task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Task 1",
            description="Task 1",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel([task])

        assert len(results) == 1
        assert results[0]["task_id"] == task.id
        assert results[0]["spec_id"] == "F001"
        assert results[0]["status"] == "success"
        assert results[0]["session_id"] is not None

    def test_run_parallel_multiple_tasks(self, db, sample_project):
        """Test run_parallel with multiple independent tasks."""
        tasks = []
        for i in range(1, 6):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                depends_on=[],
            )
            db.create_task(task)
            tasks.append(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel(tasks, max_workers=3)

        # Should have results for all tasks
        assert len(results) == 5

        # All should be successful
        for result in results:
            assert result["status"] == "success"
            assert result["session_id"] is not None
            assert result["task_id"] in [t.id for t in tasks]

        # Verify sessions were created in database
        sessions = db.list_sessions(project_id=sample_project.id)
        assert len(sessions) == 5

    def test_run_parallel_creates_separate_sessions(self, db, sample_project):
        """Test that run_parallel creates a separate session for each task."""
        tasks = []
        for i in range(1, 4):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                depends_on=[],
            )
            db.create_task(task)
            tasks.append(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel(tasks, max_workers=2)

        # Extract session IDs
        session_ids = [r["session_id"] for r in results]

        # All session IDs should be unique
        assert len(session_ids) == len(set(session_ids))

        # Verify each session links to correct task
        for result in results:
            session = db.get_session(result["session_id"])
            assert session is not None
            assert session.task_id == result["task_id"]
            assert session.project_id == sample_project.id

    def test_run_parallel_handles_individual_failures(self, db, sample_project):
        """Test that failures in individual tasks don't stop others."""
        tasks = []
        for i in range(1, 4):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                depends_on=[],
            )
            db.create_task(task)
            tasks.append(task)

        # Custom executor that fails on second task
        def failing_executor(task: Task) -> dict:
            if task.spec_id == "F002":
                raise ValueError("Simulated task failure")
            return {"status": "success"}

        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel(tasks, executor_func=failing_executor)

        # Should have results for all tasks
        assert len(results) == 3

        # Check individual results
        results_by_spec = {r["spec_id"]: r for r in results}

        # F001 should succeed
        assert results_by_spec["F001"]["status"] == "success"

        # F002 should fail
        assert results_by_spec["F002"]["status"] == "error"
        assert "Simulated task failure" in results_by_spec["F002"]["error"]

        # F003 should succeed (not affected by F002 failure)
        assert results_by_spec["F003"]["status"] == "success"

    def test_run_parallel_with_custom_executor(self, db, sample_project):
        """Test run_parallel with custom executor function."""
        task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Task 1",
            description="Task 1",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(task)

        # Custom executor that returns custom data
        def custom_executor(task: Task) -> dict:
            return {
                "status": "success",
                "custom_data": f"Processed {task.spec_id}",
            }

        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel([task], executor_func=custom_executor)

        assert len(results) == 1
        assert results[0]["status"] == "success"

    def test_run_parallel_respects_max_workers(self, db, sample_project):
        """Test that run_parallel respects max_workers parameter."""
        import threading
        import time

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0
        lock = threading.Lock()

        def tracking_executor(task: Task) -> dict:
            nonlocal concurrent_count, max_concurrent

            with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)

            time.sleep(0.05)  # Simulate work

            with lock:
                concurrent_count -= 1

            return {"status": "success"}

        # Create 10 tasks
        tasks = []
        for i in range(1, 11):
            task = Task(
                id=f"task-{i:03d}",
                project_id=sample_project.id,
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.PENDING,
                depends_on=[],
            )
            db.create_task(task)
            tasks.append(task)

        queue = TaskQueue(db, project_id=sample_project.id)

        # Run with max_workers=3
        results = queue.run_parallel(tasks, max_workers=3, executor_func=tracking_executor)

        assert len(results) == 10
        # Max concurrent should not exceed max_workers
        assert max_concurrent <= 3

    def test_run_parallel_returns_timing_info(self, db, sample_project):
        """Test that run_parallel returns timing information."""
        task = Task(
            id="task-001",
            project_id=sample_project.id,
            spec_id="F001",
            title="Task 1",
            description="Task 1",
            status=TaskStatus.PENDING,
            depends_on=[],
        )
        db.create_task(task)

        queue = TaskQueue(db, project_id=sample_project.id)
        results = queue.run_parallel([task])

        assert len(results) == 1
        result = results[0]

        # Check timing fields exist
        assert "started_at" in result
        assert "completed_at" in result

        # Verify they're valid ISO timestamps
        from datetime import datetime
        started = datetime.fromisoformat(result["started_at"])
        completed = datetime.fromisoformat(result["completed_at"])

        # Completed should be after started
        assert completed >= started
