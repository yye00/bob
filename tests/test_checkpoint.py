"""Tests for CheckpointManager module.

Tests the session checkpointing system for enabling resume capability.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bob.database.manager import DatabaseManager
from bob.models.base import (
    AgentType,
    ModelTier,
    Project,
    ProjectStatus,
    Session,
    SessionStatus,
    Task,
    TaskStatus,
)
from bob.orchestrator.checkpoint import CheckpointManager


@pytest.fixture
def db_manager(tmp_path):
    """Create a temporary database manager for testing."""
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path)


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def project(db_manager, workspace):
    """Create a test project."""
    proj = Project(
        id="proj-test",
        name="test-project",
        description="Test project for checkpoints",
        workspace_dir=str(workspace),
        spec_source="file://test.yaml",
    )
    project_id = db_manager.create_project(proj)
    return db_manager.get_project(project_id)


@pytest.fixture
def session(db_manager, project):
    """Create a test session."""
    sess = Session(
        id="session-test",
        project_id=project.id,
        task_id=None,  # No task for this test session
        agent_type=AgentType.CODING,
        model="claude-sonnet-4-5-20250929",
        started_at=datetime.now(timezone.utc),
    )
    session_id = db_manager.create_session(sess)
    return db_manager.get_session(session_id)


@pytest.fixture
def task(db_manager, project):
    """Create a test task."""
    task_obj = Task(
        id="task-test",
        project_id=project.id,
        spec_id="F001",
        title="Test task",
        description="Test task for checkpoints",
        priority="high",
    )
    task_id = db_manager.create_task(task_obj)
    return db_manager.get_task(task_id)


@pytest.fixture
def checkpoint_manager(db_manager, workspace):
    """Create a checkpoint manager."""
    return CheckpointManager(db_manager, workspace)


class TestCheckpointManagerInit:
    """Test CheckpointManager initialization."""

    def test_init_creates_checkpoint_directory(self, db_manager, workspace):
        """Test that initialization creates checkpoint directory."""
        manager = CheckpointManager(db_manager, workspace)

        checkpoint_dir = workspace / ".bob" / "checkpoints"
        assert checkpoint_dir.exists()
        assert checkpoint_dir.is_dir()

    def test_init_with_custom_interval(self, db_manager, workspace):
        """Test initialization with custom checkpoint interval."""
        manager = CheckpointManager(db_manager, workspace, checkpoint_interval=10)
        assert manager.checkpoint_interval == 10

    def test_init_with_default_interval(self, db_manager, workspace):
        """Test initialization with default checkpoint interval."""
        manager = CheckpointManager(db_manager, workspace)
        assert manager.checkpoint_interval == 5


class TestSaveCheckpoint:
    """Test checkpoint saving."""

    def test_save_checkpoint_creates_file(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that save_checkpoint creates a checkpoint file."""
        conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, conversation_history
        )

        # Verify checkpoint file exists
        checkpoint_path = checkpoint_manager.get_checkpoint_path(checkpoint_id)
        assert checkpoint_path.exists()

        # Verify file contains valid JSON
        with open(checkpoint_path) as f:
            data = json.load(f)

        assert data["checkpoint_id"] == checkpoint_id
        assert data["session_id"] == session.id

    def test_save_checkpoint_stores_conversation(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that checkpoint stores conversation history."""
        conversation_history = [
            {"role": "user", "content": "Write a function"},
            {"role": "assistant", "content": "Here's the function..."},
            {"role": "user", "content": "Add tests"},
        ]

        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, conversation_history
        )

        # Restore and verify
        data = checkpoint_manager.restore_checkpoint(checkpoint_id)
        assert data["conversation_history"] == conversation_history
        assert data["turn_count"] == 3

    def test_save_checkpoint_stores_session_data(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that checkpoint stores session metadata."""
        conversation_history = [{"role": "user", "content": "Test"}]

        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, conversation_history
        )

        data = checkpoint_manager.restore_checkpoint(checkpoint_id)

        assert data["session"]["id"] == session.id
        assert data["session"]["project_id"] == session.project_id
        assert data["session"]["model"] == session.model
        assert data["session"]["agent_type"] == AgentType.CODING.value

    def test_save_checkpoint_with_task(
        self, checkpoint_manager, session, task, db_manager
    ):
        """Test checkpoint with associated task."""
        # Create a new session with task_id
        from bob.models.base import Session, AgentType
        from datetime import datetime, timezone

        sess_with_task = Session(
            id="session-with-task",
            project_id=session.project_id,
            task_id=task.id,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4-5-20250929",
            started_at=datetime.now(timezone.utc),
        )
        db_manager.create_session(sess_with_task)
        session = db_manager.get_session("session-with-task")

        conversation_history = [{"role": "user", "content": "Test"}]

        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, conversation_history
        )

        data = checkpoint_manager.restore_checkpoint(checkpoint_id)

        assert "task" in data
        assert data["task"]["id"] == task.id
        assert data["task"]["spec_id"] == task.spec_id
        assert data["task"]["title"] == task.title

    def test_save_checkpoint_with_metadata(
        self, checkpoint_manager, session, db_manager
    ):
        """Test checkpoint with custom metadata."""
        conversation_history = [{"role": "user", "content": "Test"}]
        metadata = {
            "custom_field": "value",
            "iteration": 5,
            "notes": "Testing metadata",
        }

        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, conversation_history, metadata=metadata
        )

        data = checkpoint_manager.restore_checkpoint(checkpoint_id)

        assert "metadata" in data
        assert data["metadata"] == metadata

    def test_save_checkpoint_invalid_session(
        self, checkpoint_manager, db_manager
    ):
        """Test save_checkpoint with invalid session ID."""
        with pytest.raises(ValueError, match="Session .* not found"):
            checkpoint_manager.save_checkpoint(
                "invalid-session", [{"role": "user", "content": "Test"}]
            )


class TestRestoreCheckpoint:
    """Test checkpoint restoration."""

    def test_restore_checkpoint_returns_data(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that restore_checkpoint returns checkpoint data."""
        conversation_history = [{"role": "user", "content": "Test"}]

        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, conversation_history
        )

        data = checkpoint_manager.restore_checkpoint(checkpoint_id)

        assert isinstance(data, dict)
        assert data["checkpoint_id"] == checkpoint_id
        assert data["session_id"] == session.id

    def test_restore_nonexistent_checkpoint(self, checkpoint_manager):
        """Test restore_checkpoint with non-existent checkpoint."""
        with pytest.raises(ValueError, match="Checkpoint .* not found"):
            checkpoint_manager.restore_checkpoint("nonexistent_checkpoint")


class TestListCheckpoints:
    """Test checkpoint listing."""

    def test_list_checkpoints_empty(self, checkpoint_manager):
        """Test list_checkpoints with no checkpoints."""
        checkpoints = checkpoint_manager.list_checkpoints()
        assert checkpoints == []

    def test_list_checkpoints_returns_metadata(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that list_checkpoints returns checkpoint metadata."""
        # Create multiple checkpoints
        for i in range(3):
            checkpoint_manager.save_checkpoint(
                session.id, [{"role": "user", "content": f"Message {i}"}]
            )

        checkpoints = checkpoint_manager.list_checkpoints()

        assert len(checkpoints) == 3
        for checkpoint in checkpoints:
            assert "checkpoint_id" in checkpoint
            assert "session_id" in checkpoint
            assert "project_id" in checkpoint
            assert "timestamp" in checkpoint
            assert "turn_count" in checkpoint

    def test_list_checkpoints_sorted_by_timestamp(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that checkpoints are sorted by timestamp (newest first)."""
        import time

        checkpoint_ids = []
        for i in range(3):
            checkpoint_id = checkpoint_manager.save_checkpoint(
                session.id, [{"role": "user", "content": f"Message {i}"}]
            )
            checkpoint_ids.append(checkpoint_id)
            time.sleep(0.01)  # Ensure different timestamps

        checkpoints = checkpoint_manager.list_checkpoints()

        # Newest should be first
        assert checkpoints[0]["checkpoint_id"] == checkpoint_ids[2]
        assert checkpoints[1]["checkpoint_id"] == checkpoint_ids[1]
        assert checkpoints[2]["checkpoint_id"] == checkpoint_ids[0]

    def test_list_checkpoints_filter_by_session(
        self, checkpoint_manager, db_manager, project
    ):
        """Test filtering checkpoints by session ID."""
        # Create two sessions
        session1 = Session(
            id="session-1",
            project_id=project.id,
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4-5-20250929",
        )
        session2 = Session(
            id="session-2",
            project_id=project.id,
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4-5-20250929",
        )
        db_manager.create_session(session1)
        db_manager.create_session(session2)

        # Create checkpoints for both sessions
        checkpoint_manager.save_checkpoint(
            "session-1", [{"role": "user", "content": "Session 1"}]
        )
        checkpoint_manager.save_checkpoint(
            "session-2", [{"role": "user", "content": "Session 2"}]
        )

        # Filter by session 1
        checkpoints = checkpoint_manager.list_checkpoints(session_id="session-1")
        assert len(checkpoints) == 1
        assert checkpoints[0]["session_id"] == "session-1"

    def test_list_checkpoints_limit(
        self, checkpoint_manager, session, db_manager
    ):
        """Test limiting number of checkpoints returned."""
        # Create 10 checkpoints
        for i in range(10):
            checkpoint_manager.save_checkpoint(
                session.id, [{"role": "user", "content": f"Message {i}"}]
            )

        # Request only 5
        checkpoints = checkpoint_manager.list_checkpoints(limit=5)
        assert len(checkpoints) == 5


class TestDeleteCheckpoint:
    """Test checkpoint deletion."""

    def test_delete_checkpoint_removes_file(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that delete_checkpoint removes the checkpoint file."""
        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, [{"role": "user", "content": "Test"}]
        )

        # Verify file exists
        checkpoint_path = checkpoint_manager.get_checkpoint_path(checkpoint_id)
        assert checkpoint_path.exists()

        # Delete checkpoint
        result = checkpoint_manager.delete_checkpoint(checkpoint_id)
        assert result is True

        # Verify file is gone
        assert not checkpoint_path.exists()

    def test_delete_nonexistent_checkpoint(self, checkpoint_manager):
        """Test delete_checkpoint with non-existent checkpoint."""
        result = checkpoint_manager.delete_checkpoint("nonexistent")
        assert result is False


class TestCleanupOldCheckpoints:
    """Test checkpoint cleanup."""

    def test_cleanup_keeps_recent(
        self, checkpoint_manager, session, db_manager
    ):
        """Test that cleanup keeps the most recent checkpoints."""
        # Create 10 checkpoints
        for i in range(10):
            checkpoint_manager.save_checkpoint(
                session.id, [{"role": "user", "content": f"Message {i}"}]
            )

        # Cleanup, keeping only 5
        deleted = checkpoint_manager.cleanup_old_checkpoints(keep_last=5)
        assert deleted == 5

        # Verify only 5 remain
        checkpoints = checkpoint_manager.list_checkpoints()
        assert len(checkpoints) == 5


class TestShouldSaveCheckpoint:
    """Test checkpoint save logic."""

    def test_should_save_at_interval(self, checkpoint_manager):
        """Test that checkpoints are saved at intervals."""
        # Default interval is 5
        assert checkpoint_manager.should_save_checkpoint(0) is False
        assert checkpoint_manager.should_save_checkpoint(5) is True
        assert checkpoint_manager.should_save_checkpoint(10) is True
        assert checkpoint_manager.should_save_checkpoint(7) is False

    def test_should_save_custom_interval(self, db_manager, workspace):
        """Test checkpoint saving with custom interval."""
        manager = CheckpointManager(db_manager, workspace, checkpoint_interval=10)

        assert manager.should_save_checkpoint(10) is True
        assert manager.should_save_checkpoint(20) is True
        assert manager.should_save_checkpoint(5) is False


class TestExportImportCheckpoint:
    """Test checkpoint export and import."""

    def test_export_checkpoint(
        self, checkpoint_manager, session, db_manager, tmp_path
    ):
        """Test exporting a checkpoint to a different location."""
        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, [{"role": "user", "content": "Test"}]
        )

        export_path = tmp_path / "exported_checkpoint.json"
        checkpoint_manager.export_checkpoint(checkpoint_id, export_path)

        assert export_path.exists()

        # Verify exported data is valid
        with open(export_path) as f:
            data = json.load(f)
        assert data["checkpoint_id"] == checkpoint_id

    def test_import_checkpoint(
        self, checkpoint_manager, session, db_manager, tmp_path
    ):
        """Test importing a checkpoint from a file."""
        # Create and export a checkpoint
        checkpoint_id = checkpoint_manager.save_checkpoint(
            session.id, [{"role": "user", "content": "Test"}]
        )

        export_path = tmp_path / "exported.json"
        checkpoint_manager.export_checkpoint(checkpoint_id, export_path)

        # Delete original
        checkpoint_manager.delete_checkpoint(checkpoint_id)

        # Import it back
        imported_id = checkpoint_manager.import_checkpoint(export_path)
        assert imported_id == checkpoint_id

        # Verify it can be restored
        data = checkpoint_manager.restore_checkpoint(imported_id)
        assert data["checkpoint_id"] == checkpoint_id

    def test_import_invalid_checkpoint(self, checkpoint_manager, tmp_path):
        """Test importing an invalid checkpoint file."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text('{"invalid": "data"}')

        with pytest.raises(ValueError, match="Invalid checkpoint"):
            checkpoint_manager.import_checkpoint(invalid_file)
