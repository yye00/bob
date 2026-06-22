"""Tests for F064: Restore from forgetting event.

Validates that:
- Step 1: restore_from_forgetting() function exists
- Step 2: Retrieve backup_content from forgetting_events
- Step 3: Recreate lesson/memory with original content
- Step 4: Set restored_at timestamp
- Step 5: Purge lesson, restore it, verify content matches original
"""

import json
import pathlib

import pytest

from bob3 import db
from bob3.models import ForgettingEvent

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project."""
    return db.create_project(
        name="F064 Test Project",
        workspace_path="/tmp/test-f064",
    )


# ===================================================================
# Step 1: restore_from_forgetting() function exists
# ===================================================================


class TestRestoreFromForgettingExists:
    """Step 1: restore_from_forgetting() must exist in db module."""

    def test_function_exists(self):
        assert hasattr(db, "restore_from_forgetting")
        assert callable(db.restore_from_forgetting)

    def test_returns_dict_with_backup_content(self, project):
        """restore_from_forgetting returns a dict with event and backup_content."""
        backup = {"text": "Lesson about error handling", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_lesson_1",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert result is not None
        assert "restore_event" in result
        assert "backup_content" in result
        assert isinstance(result["restore_event"], ForgettingEvent)

    def test_returns_none_for_nonexistent_event(self):
        """Returns None when event_id does not exist."""
        result = db.restore_from_forgetting("nonexistent-id")
        assert result is None


# ===================================================================
# Step 2: Retrieve backup_content from forgetting_events
# ===================================================================


class TestRetrieveBackupContent:
    """Step 2: backup_content is retrieved from the original purge event."""

    def test_backup_content_matches_original(self, project):
        backup = {
            "text": "Always use WAL mode for concurrent reads",
            "pool": "lessons",
            "metadata": {"feature_id": "F004"},
        }
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_lesson_wal",
            action="purge",
            reason="Outdated",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        parsed = json.loads(result["backup_content"])
        assert parsed["text"] == "Always use WAL mode for concurrent reads"
        assert parsed["pool"] == "lessons"
        assert parsed["metadata"]["feature_id"] == "F004"

    def test_fails_when_no_backup_content(self, project):
        """Cannot restore from event without backup_content."""
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="no_backup",
            action="purge",
            reason="Purged without backup",
            can_restore=False,
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert result is None

    def test_fails_for_non_purge_event(self, project):
        """Cannot restore from a demote or archive event (no backup_content)."""
        demote_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="demoted_lesson",
            action="demote",
            reason="Low score",
        )

        result = db.restore_from_forgetting(demote_event.id)
        assert result is None


# ===================================================================
# Step 3: Recreate lesson/memory with original content
# ===================================================================


class TestRecreateContent:
    """Step 3: A restore forgetting event is created with the original content."""

    def test_creates_restore_event(self, project):
        backup = {"text": "Lesson content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_restore_1",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        restore_event = result["restore_event"]
        assert restore_event.action == "restore"
        assert restore_event.target_type == "lesson"
        assert restore_event.target_id == "titans_restore_1"

    def test_restore_event_has_project_id(self, project):
        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_proj_restore",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert result["restore_event"].project_id == project.id

    def test_restore_event_reason_references_original(self, project):
        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_reason_test",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert purge_event.id in result["restore_event"].reason

    def test_restore_event_triggered_by_system(self, project):
        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_trigger_test",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert result["restore_event"].triggered_by == "system"

    def test_restore_event_visible_in_events_list(self, project):
        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_list_test",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        db.restore_from_forgetting(purge_event.id)

        events = db.get_forgetting_events(
            project_id=project.id,
            target_id="titans_list_test",
        )
        actions = [e.action for e in events]
        assert "purge" in actions
        assert "restore" in actions


# ===================================================================
# Step 4: Set restored_at timestamp
# ===================================================================


class TestRestoredAtTimestamp:
    """Step 4: The original purge event gets restored_at set."""

    def test_original_purge_event_has_restored_at(self, project):
        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_ts_test",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )
        assert purge_event.restored_at is None

        db.restore_from_forgetting(purge_event.id)

        updated = db.get_forgetting_event(purge_event.id)
        assert updated.restored_at is not None

    def test_restored_at_is_recent(self, project):
        from datetime import datetime, timedelta

        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_recent_test",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        before = datetime.now()
        db.restore_from_forgetting(purge_event.id)

        updated = db.get_forgetting_event(purge_event.id)
        assert updated.restored_at >= before - timedelta(seconds=5)


# ===================================================================
# Step 5: Purge lesson, restore it, verify content matches original
# ===================================================================


class TestFullRestoreWorkflow:
    """Step 5: End-to-end purge and restore workflow."""

    def test_purge_then_restore_preserves_content(self, project):
        """Full integration: purge a lesson, then restore it and verify
        the backup_content matches the original."""
        original_lesson = {
            "text": "When SQLite WAL mode is enabled, concurrent reads are possible "
            "without blocking writes. This is critical for multi-agent workloads.",
            "pool": "lessons",
            "metadata": {
                "feature_id": "F004",
                "trigger": "database connection issues during parallel execution",
                "solution": "Enable WAL mode with PRAGMA journal_mode=WAL",
            },
        }

        # Step 1: Purge the lesson with backup
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_lesson_42",
            action="purge",
            reason="Lesson obsoleted by new architecture",
            previous_status="archived",
            previous_usefulness_score=0.15,
            previous_retrieval_weight=0.1,
            backup_content=json.dumps(original_lesson),
            backup_path="/backups/titans_lesson_42.json",
            triggered_by="manual",
            approved_by="senior_engineer",
        )

        # Step 2: Restore from the purge event
        result = db.restore_from_forgetting(purge_event.id)
        assert result is not None

        # Step 3: Verify backup_content matches original
        restored_content = json.loads(result["backup_content"])
        assert restored_content["text"] == original_lesson["text"]
        assert restored_content["pool"] == original_lesson["pool"]
        assert restored_content["metadata"]["feature_id"] == "F004"
        assert "WAL mode" in restored_content["metadata"]["solution"]

        # Step 4: Verify restore event was created
        restore_event = result["restore_event"]
        assert restore_event.action == "restore"
        assert restore_event.target_id == "titans_lesson_42"
        assert restore_event.target_type == "lesson"

        # Step 5: Verify original purge event now has restored_at
        updated_purge = db.get_forgetting_event(purge_event.id)
        assert updated_purge.restored_at is not None

    def test_restore_memory_type(self, project):
        """Can restore memory type, not just lessons."""
        original_memory = {
            "text": "Project uses Python 3.13 with asyncio",
            "pool": "context",
        }
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="memory",
            target_id="mem_ctx_99",
            action="purge",
            reason="Context no longer relevant",
            backup_content=json.dumps(original_memory),
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert result is not None
        restored = json.loads(result["backup_content"])
        assert restored["text"] == original_memory["text"]
        assert result["restore_event"].target_type == "memory"

    def test_cannot_restore_already_restored(self, project):
        """Cannot restore from an event that has already been restored."""
        backup = {"text": "Content", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="already_restored",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        # First restore succeeds
        result1 = db.restore_from_forgetting(purge_event.id)
        assert result1 is not None

        # Second restore fails (already restored)
        result2 = db.restore_from_forgetting(purge_event.id)
        assert result2 is None

    def test_restore_without_project_id(self):
        """Can restore from event that has no project_id."""
        backup = {"text": "Orphan lesson", "pool": "lessons"}
        purge_event = db.record_forgetting_event(
            target_type="lesson",
            target_id="orphan_lesson",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )

        result = db.restore_from_forgetting(purge_event.id)
        assert result is not None
        assert result["restore_event"].project_id is None
        restored = json.loads(result["backup_content"])
        assert restored["text"] == "Orphan lesson"
