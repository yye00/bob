"""Functional tests for database operations."""
import pytest
from pathlib import Path
from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus, Project, ProjectStatus


class TestDatabaseFunctional:
    """Test database operations work correctly end-to-end."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a real database for testing."""
        db_path = tmp_path / "test.db"
        return DatabaseManager(db_path)

    def test_create_and_retrieve_project(self, db, tmp_path):
        """Test project creation and retrieval actually persists data."""
        # Create project
        project = Project(
            id="test-proj-001",
            name="test-project",
            description="Test project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        assert project_id is not None

        # Retrieve and verify
        retrieved = db.get_project(project_id)
        assert retrieved is not None
        assert retrieved.name == "test-project"
        assert retrieved.workspace_dir == str(tmp_path)

    def test_create_and_retrieve_task(self, db, tmp_path):
        """Test task creation and retrieval actually persists data."""
        # Create project first
        project = Project(
            id="test-proj-002",
            name="test-project",
            description="Test project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)

        # Create task
        task = Task(
            id="task-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            priority="high",
        )
        task_id = db.create_task(task)
        assert task_id is not None

        # Retrieve and verify
        retrieved = db.get_task(task_id)
        assert retrieved is not None
        assert retrieved.spec_id == "F001"
        assert retrieved.title == "Test Task"
        assert retrieved.status == TaskStatus.PENDING

    def test_update_task_status(self, db, tmp_path):
        """Test task status updates persist correctly."""
        # Setup
        project = Project(
            id="test-proj-003",
            name="test-project",
            description="Test project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        
        task = Task(
            id="task-002",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        task_id = db.create_task(task)

        # Update status
        db.update_task(task_id, status=TaskStatus.IN_PROGRESS)

        # Verify update persisted
        retrieved = db.get_task(task_id)
        assert retrieved.status == TaskStatus.IN_PROGRESS

    def test_get_active_project(self, db, tmp_path):
        """Test get_active_project returns the correct project."""
        # Create and set active project
        project = Project(
            id="test-proj-004",
            name="active-project",
            description="Active project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        db.set_active_project(project_id)

        # Retrieve active project
        active = db.get_active_project()
        assert active is not None
        assert active.id == project_id
        assert active.name == "active-project"

    def test_log_event(self, db, tmp_path):
        """Test event logging works correctly (no error when logging)."""
        project = Project(
            id="test-proj-005",
            name="test-project",
            description="Test project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        
        # Log an event - if this doesn't raise, logging works
        db.log_event(
            event_type="test_event",
            project_id=project_id,
            data={"message": "Test event logged"},
        )
        
        # Verify by checking the events table directly
        with db.connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM events WHERE project_id = ?",
                (project_id,)
            )
            events = cursor.fetchall()
        assert len(events) >= 1

    def test_task_dependencies(self, db, tmp_path):
        """Test task dependency tracking works."""
        project = Project(
            id="test-proj-006",
            name="test-project",
            description="Test project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        
        # Create parent task
        parent = Task(
            id="task-parent",
            project_id=project_id,
            spec_id="F001",
            title="Parent Task",
            description="Parent",
        )
        db.create_task(parent)
        
        # Create child task with dependency
        child = Task(
            id="task-child",
            project_id=project_id,
            spec_id="F002",
            title="Child Task",
            description="Child",
            depends_on=["F001"],
        )
        child_id = db.create_task(child)

        # Verify dependency relationship
        retrieved = db.get_task(child_id)
        assert "F001" in retrieved.depends_on
