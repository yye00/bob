"""Tests for database manager.

Tests CRUD operations, transactions, and query methods for all entities.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from bob.database import DatabaseManager
from bob.models.base import (
    AgentType,
    FailureType,
    ModelTier,
    Project,
    ProjectStatus,
    Session,
    SessionStatus,
    Task,
    TaskStatus,
)


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(db_path)
        yield manager


class TestDatabaseManagerInit:
    """Test database initialization."""

    def test_init_creates_schema(self, db):
        """Test that initializing creates the schema."""
        # Should be able to connect and query
        with db.connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}
            assert "projects" in tables
            assert "tasks" in tables
            assert "sessions" in tables

    def test_foreign_keys_enabled(self, db):
        """Test that foreign keys are enabled."""
        with db.connect() as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            assert cursor.fetchone()[0] == 1


class TestProjectCRUD:
    """Test project CRUD operations."""

    def test_create_project(self, db):
        """Test creating a project."""
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        project_id = db.create_project(project)
        assert project_id == "proj-1"

    def test_get_project(self, db):
        """Test retrieving a project."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
            config={"key": "value"},
        )
        db.create_project(project)

        # Retrieve it
        retrieved = db.get_project("proj-1")
        assert retrieved is not None
        assert retrieved.id == "proj-1"
        assert retrieved.name == "Test Project"
        assert retrieved.description == "A test project"
        assert retrieved.config == {"key": "value"}
        assert retrieved.status == ProjectStatus.ACTIVE

    def test_get_project_not_found(self, db):
        """Test retrieving a non-existent project."""
        result = db.get_project("nonexistent")
        assert result is None

    def test_list_projects(self, db):
        """Test listing projects."""
        # Create multiple projects
        for i in range(5):
            project = Project(
                id=f"proj-{i}",
                name=f"Project {i}",
                description=f"Description {i}",
                workspace_dir=f"/tmp/proj{i}",
                spec_source="file://spec.yaml",
                status=ProjectStatus.ACTIVE if i % 2 == 0 else ProjectStatus.PAUSED,
            )
            db.create_project(project)

        # List all projects
        projects = db.list_projects()
        assert len(projects) == 5

        # List only active projects
        active_projects = db.list_projects(status=ProjectStatus.ACTIVE)
        assert len(active_projects) == 3

        # Test pagination
        page1 = db.list_projects(limit=2, offset=0)
        assert len(page1) == 2
        page2 = db.list_projects(limit=2, offset=2)
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    def test_update_project(self, db):
        """Test updating a project."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="Original description",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Update it
        success = db.update_project(
            "proj-1",
            name="Updated Project",
            description="Updated description",
            status=ProjectStatus.COMPLETED,
            config={"updated": True},
        )
        assert success

        # Verify updates
        updated = db.get_project("proj-1")
        assert updated.name == "Updated Project"
        assert updated.description == "Updated description"
        assert updated.status == ProjectStatus.COMPLETED
        assert updated.config == {"updated": True}

    def test_update_project_partial(self, db):
        """Test partial update of a project."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="Original description",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Update only status
        success = db.update_project("proj-1", status=ProjectStatus.PAUSED)
        assert success

        # Verify only status changed
        updated = db.get_project("proj-1")
        assert updated.name == "Test Project"  # Unchanged
        assert updated.description == "Original description"  # Unchanged
        assert updated.status == ProjectStatus.PAUSED  # Changed

    def test_update_project_not_found(self, db):
        """Test updating a non-existent project."""
        success = db.update_project("nonexistent", name="New Name")
        assert not success

    def test_delete_project(self, db):
        """Test deleting a project."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Delete it
        success = db.delete_project("proj-1")
        assert success

        # Verify it's gone
        result = db.get_project("proj-1")
        assert result is None

    def test_delete_project_not_found(self, db):
        """Test deleting a non-existent project."""
        success = db.delete_project("nonexistent")
        assert not success

    def test_delete_project_cascades(self, db):
        """Test that deleting a project cascades to tasks and sessions."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Create task
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        db.create_task(task)

        # Create session
        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id="task-1",
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
        )
        db.create_session(session)

        # Delete project
        db.delete_project("proj-1")

        # Verify task and session are also deleted
        assert db.get_task("task-1") is None
        assert db.get_session("sess-1") is None


class TestTaskCRUD:
    """Test task CRUD operations."""

    def test_create_task(self, db):
        """Test creating a task."""
        # Create project first
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Create task
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        task_id = db.create_task(task)
        assert task_id == "task-1"

    def test_get_task(self, db):
        """Test retrieving a task."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Create task
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            steps=["Step 1", "Step 2"],
            depends_on=["task-0"],
            priority="high",
            category="functional",
            labels=["backend", "api"],
            research_required=True,
            research_queries=["Query 1", "Query 2"],
        )
        db.create_task(task)

        # Retrieve it
        retrieved = db.get_task("task-1")
        assert retrieved is not None
        assert retrieved.id == "task-1"
        assert retrieved.project_id == "proj-1"
        assert retrieved.spec_id == "F001"
        assert retrieved.title == "Test Task"
        assert retrieved.acceptance_criteria == ["Criterion 1", "Criterion 2"]
        assert retrieved.steps == ["Step 1", "Step 2"]
        assert retrieved.depends_on == ["task-0"]
        assert retrieved.priority == "high"
        assert retrieved.category == "functional"
        assert retrieved.labels == ["backend", "api"]
        assert retrieved.research_required is True
        assert retrieved.research_queries == ["Query 1", "Query 2"]

    def test_list_tasks(self, db):
        """Test listing tasks."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Create multiple tasks
        for i in range(5):
            task = Task(
                id=f"task-{i}",
                project_id="proj-1",
                spec_id=f"F{i:03d}",
                title=f"Task {i}",
                description=f"Description {i}",
                priority="critical" if i == 0 else "high" if i == 1 else "medium",
                status=TaskStatus.PENDING if i % 2 == 0 else TaskStatus.COMPLETED,
            )
            db.create_task(task)

        # List all tasks
        tasks = db.list_tasks()
        assert len(tasks) == 5

        # Verify priority ordering (critical first)
        assert tasks[0].priority == "critical"
        assert tasks[1].priority == "high"

        # Filter by project
        project_tasks = db.list_tasks(project_id="proj-1")
        assert len(project_tasks) == 5

        # Filter by status
        pending_tasks = db.list_tasks(status=TaskStatus.PENDING)
        assert len(pending_tasks) == 3

        # Filter by priority
        critical_tasks = db.list_tasks(priority="critical")
        assert len(critical_tasks) == 1

    def test_update_task(self, db):
        """Test updating a task."""
        # Create project and task
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        db.create_task(task)

        # Update task
        success = db.update_task(
            "task-1",
            status=TaskStatus.IN_PROGRESS,
            assigned_agent=AgentType.CODING,
            current_model="claude-opus-4",
            escalation_tier=ModelTier.TIER2,
            failure_type=FailureType.COMPLEXITY,
            research_required=True,
            research_complete=False,
            research_findings={"finding": "data"},
            attempts=3,
        )
        assert success

        # Verify updates
        updated = db.get_task("task-1")
        assert updated.status == TaskStatus.IN_PROGRESS
        assert updated.assigned_agent == AgentType.CODING
        assert updated.current_model == "claude-opus-4"
        assert updated.escalation_tier == ModelTier.TIER2
        assert updated.failure_type == FailureType.COMPLEXITY
        assert updated.research_required is True
        assert updated.research_complete is False
        assert updated.research_findings == {"finding": "data"}
        assert updated.attempts == 3

    def test_delete_task(self, db):
        """Test deleting a task."""
        # Create project and task
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        db.create_task(task)

        # Delete task
        success = db.delete_task("task-1")
        assert success

        # Verify it's gone
        result = db.get_task("task-1")
        assert result is None


class TestSessionCRUD:
    """Test session CRUD operations."""

    def test_create_session(self, db):
        """Test creating a session."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Create session
        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.INITIALIZER,
            model="claude-sonnet-4",
        )
        session_id = db.create_session(session)
        assert session_id == "sess-1"

    def test_get_session(self, db):
        """Test retrieving a session."""
        # Create project
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        # Create session with stats
        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            turns=10,
            tokens={"input": 5000, "output": 3000},
            cost=0.025,
        )
        db.create_session(session)

        # Retrieve it
        retrieved = db.get_session("sess-1")
        assert retrieved is not None
        assert retrieved.id == "sess-1"
        assert retrieved.project_id == "proj-1"
        assert retrieved.agent_type == AgentType.CODING
        assert retrieved.model == "claude-sonnet-4"
        assert retrieved.turns == 10
        assert retrieved.tokens == {"input": 5000, "output": 3000}
        assert retrieved.cost == 0.025

    def test_list_sessions(self, db):
        """Test listing sessions."""
        # Create project and task
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        db.create_task(task)

        # Create multiple sessions
        for i in range(5):
            session = Session(
                id=f"sess-{i}",
                project_id="proj-1",
                task_id="task-1" if i % 2 == 0 else None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.RUNNING if i % 2 == 0 else SessionStatus.COMPLETED,
            )
            db.create_session(session)

        # List all sessions
        sessions = db.list_sessions()
        assert len(sessions) == 5

        # Filter by project
        project_sessions = db.list_sessions(project_id="proj-1")
        assert len(project_sessions) == 5

        # Filter by task
        task_sessions = db.list_sessions(task_id="task-1")
        assert len(task_sessions) == 3

        # Filter by status
        running_sessions = db.list_sessions(status=SessionStatus.RUNNING)
        assert len(running_sessions) == 3

    def test_update_session(self, db):
        """Test updating a session."""
        # Create project and session
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
        )
        db.create_session(session)

        # Update session
        ended_at = datetime.now()
        success = db.update_session(
            "sess-1",
            status=SessionStatus.COMPLETED,
            ended_at=ended_at,
            turns=15,
            tokens={"input": 8000, "output": 5000},
            cost=0.035,
        )
        assert success

        # Verify updates
        updated = db.get_session("sess-1")
        assert updated.status == SessionStatus.COMPLETED
        assert updated.ended_at is not None
        assert updated.turns == 15
        assert updated.tokens == {"input": 8000, "output": 5000}
        assert updated.cost == 0.035

    def test_delete_session(self, db):
        """Test deleting a session."""
        # Create project and session
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        db.create_project(project)

        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
        )
        db.create_session(session)

        # Delete session
        success = db.delete_session("sess-1")
        assert success

        # Verify it's gone
        result = db.get_session("sess-1")
        assert result is None


class TestTransactions:
    """Test transaction support."""

    def test_transaction_commit(self, db):
        """Test that successful transactions commit."""
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )

        # Use transaction context manager
        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, name, description, workspace_dir, spec_source, config, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.description,
                    project.workspace_dir,
                    project.spec_source,
                    "{}",
                    project.status.value,
                ),
            )

        # Verify it was committed
        result = db.get_project("proj-1")
        assert result is not None

    def test_transaction_rollback(self, db):
        """Test that failed transactions rollback."""
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )

        # Try a transaction that will fail
        try:
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO projects (
                        id, name, description, workspace_dir, spec_source, config, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project.id,
                        project.name,
                        project.description,
                        project.workspace_dir,
                        project.spec_source,
                        "{}",
                        project.status.value,
                    ),
                )
                # Force an error
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Verify it was rolled back
        result = db.get_project("proj-1")
        assert result is None
