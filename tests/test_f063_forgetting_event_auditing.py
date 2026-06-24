"""Tests for F063: Forgetting event auditing.

Validates that:
- Step 1: record_forgetting_event() function exists and works
- Step 2: Store action (demote/archive/purge/restore)
- Step 3: Backup content for purge operations
- Step 4: Track triggered_by and approved_by
- Step 5: Purge lesson, verify forgetting_event created with backup
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
        name="F063 Test Project",
        workspace_path="/tmp/test-f063",
    )


# ===================================================================
# Step 1: record_forgetting_event() function exists and works
# ===================================================================


class TestRecordForgettingEventExists:
    """Step 1: record_forgetting_event() must exist and create forgetting_events rows."""

    def test_function_exists(self):
        assert hasattr(db, "record_forgetting_event")
        assert callable(db.record_forgetting_event)

    def test_creates_forgetting_event_record(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_mem_123",
            action="demote",
            reason="Low usefulness score after 30 days",
        )
        assert isinstance(event, ForgettingEvent)
        assert event.target_type == "lesson"
        assert event.target_id == "titans_mem_123"

    def test_returns_event_with_id(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_mem_456",
            action="demote",
            reason="Irrelevant",
        )
        assert event.id is not None
        assert len(event.id) > 0

    def test_stores_reason(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="memory",
            target_id="mem_789",
            action="archive",
            reason="Superseded by newer memory",
        )
        assert event.reason == "Superseded by newer memory"

    def test_created_at_is_set(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_100",
            action="demote",
            reason="Test",
        )
        assert event.created_at is not None

    def test_project_id_is_optional(self):
        """Can create forgetting event without project_id."""
        event = db.record_forgetting_event(
            target_type="lesson",
            target_id="mem_orphan",
            action="archive",
            reason="Orphaned lesson",
        )
        assert event.project_id is None
        assert event.target_id == "mem_orphan"


# ===================================================================
# Step 2: Store action (demote/archive/purge/restore)
# ===================================================================


class TestForgettingActions:
    """Step 2: All four action types are stored correctly."""

    def test_demote_action(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_1",
            action="demote",
            reason="Low usefulness",
            previous_status="active",
            previous_usefulness_score=0.3,
            previous_retrieval_weight=0.5,
        )
        assert event.action == "demote"
        assert event.previous_status == "active"
        assert event.previous_usefulness_score == 0.3
        assert event.previous_retrieval_weight == 0.5

    def test_archive_action(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="memory",
            target_id="mem_2",
            action="archive",
            reason="No longer relevant",
            previous_status="demoted",
        )
        assert event.action == "archive"
        assert event.previous_status == "demoted"

    def test_purge_action(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_3",
            action="purge",
            reason="Contains outdated information",
            backup_content=json.dumps({"text": "Old lesson content", "pool": "lessons"}),
        )
        assert event.action == "purge"
        assert event.backup_content is not None

    def test_restore_action(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_4",
            action="restore",
            reason="Needed again for new project",
        )
        assert event.action == "restore"

    def test_can_restore_defaults_true(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_5",
            action="demote",
            reason="Test",
        )
        assert event.can_restore is True

    def test_can_restore_false_for_purge_without_backup(self, project):
        """When purging without backup, can_restore should be False."""
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_6",
            action="purge",
            reason="Permanent removal",
            can_restore=False,
        )
        assert event.can_restore is False


# ===================================================================
# Step 3: Backup content for purge operations
# ===================================================================


class TestPurgeBackupContent:
    """Step 3: Purge operations store backup content for recovery."""

    def test_backup_content_stored_as_json(self, project):
        backup = {
            "text": "Important lesson about error handling",
            "pool": "lessons",
            "metadata": {"feature_id": "F042", "created_at": "2026-01-15"},
        }
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_purge_1",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps(backup),
        )
        assert event.backup_content is not None
        parsed = json.loads(event.backup_content)
        assert parsed["text"] == "Important lesson about error handling"
        assert parsed["pool"] == "lessons"

    def test_backup_path_stored(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_purge_2",
            action="purge",
            reason="Cleanup",
            backup_path="/backups/mem_purge_2.json",
            backup_content=json.dumps({"text": "backup"}),
        )
        assert event.backup_path == "/backups/mem_purge_2.json"

    def test_previous_state_preserved(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_purge_3",
            action="purge",
            reason="Obsolete",
            previous_status="archived",
            previous_usefulness_score=0.1,
            previous_retrieval_weight=0.2,
            backup_content=json.dumps({"text": "old content"}),
        )
        assert event.previous_status == "archived"
        assert event.previous_usefulness_score == 0.1
        assert event.previous_retrieval_weight == 0.2


# ===================================================================
# Step 4: Track triggered_by and approved_by
# ===================================================================


class TestTriggeredByApprovedBy:
    """Step 4: triggered_by and approved_by fields are tracked."""

    def test_triggered_by_schedule(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_sched_1",
            action="demote",
            reason="Scheduled cleanup",
            triggered_by="schedule",
        )
        assert event.triggered_by == "schedule"

    def test_triggered_by_manual(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="memory",
            target_id="mem_manual_1",
            action="archive",
            reason="Manual cleanup",
            triggered_by="manual",
        )
        assert event.triggered_by == "manual"

    def test_triggered_by_system(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_sys_1",
            action="demote",
            reason="Auto-demoted by system",
            triggered_by="system",
        )
        assert event.triggered_by == "system"

    def test_approved_by_for_purge(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_approved_1",
            action="purge",
            reason="Approved for removal",
            triggered_by="manual",
            approved_by="human_reviewer",
            backup_content=json.dumps({"text": "content"}),
        )
        assert event.approved_by == "human_reviewer"

    def test_approved_by_defaults_none(self, project):
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_no_approver",
            action="demote",
            reason="Auto action",
            triggered_by="system",
        )
        assert event.approved_by is None


# ===================================================================
# Step 5: Purge lesson, verify forgetting_event created with backup
# ===================================================================


class TestPurgeLessonIntegration:
    """Step 5: Full integration - purge a lesson and verify the event has backup."""

    def test_purge_lesson_creates_event_with_backup(self, project):
        """Simulate purging a TITANS lesson and verify the forgetting event
        has the correct action, backup content, triggered_by, and approved_by."""
        lesson_content = {
            "text": "When SQLite WAL mode is enabled, concurrent reads are possible",
            "pool": "lessons",
            "metadata": {
                "feature_id": "F004",
                "trigger": "database connection issues",
            },
        }

        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="titans_lesson_42",
            action="purge",
            reason="Lesson obsoleted by new architecture",
            previous_status="archived",
            previous_usefulness_score=0.15,
            previous_retrieval_weight=0.1,
            backup_content=json.dumps(lesson_content),
            backup_path="/backups/titans_lesson_42.json",
            triggered_by="manual",
            approved_by="senior_engineer",
        )

        # Verify event was created
        assert isinstance(event, ForgettingEvent)
        assert event.action == "purge"

        # Verify backup content
        assert event.backup_content is not None
        backup = json.loads(event.backup_content)
        assert "SQLite WAL mode" in backup["text"]
        assert backup["pool"] == "lessons"

        # Verify audit trail
        assert event.triggered_by == "manual"
        assert event.approved_by == "senior_engineer"

        # Verify previous state
        assert event.previous_status == "archived"
        assert event.previous_usefulness_score == 0.15

        # Verify backup path
        assert event.backup_path == "/backups/titans_lesson_42.json"

        # Verify can_restore is True (because backup exists)
        assert event.can_restore is True

    def test_get_forgetting_events_returns_all_for_project(self, project):
        """get_forgetting_events returns all events for a project."""
        db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_a",
            action="demote",
            reason="Reason A",
        )
        db.record_forgetting_event(
            project_id=project.id,
            target_type="memory",
            target_id="mem_b",
            action="archive",
            reason="Reason B",
        )

        events = db.get_forgetting_events(project_id=project.id)
        assert len(events) == 2
        assert all(isinstance(e, ForgettingEvent) for e in events)

    def test_get_forgetting_events_by_target(self, project):
        """get_forgetting_events can filter by target_id."""
        db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="specific_target",
            action="demote",
            reason="First action",
        )
        db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="specific_target",
            action="archive",
            reason="Second action",
        )
        db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="other_target",
            action="demote",
            reason="Different target",
        )

        events = db.get_forgetting_events(
            project_id=project.id,
            target_id="specific_target",
        )
        assert len(events) == 2
        assert all(e.target_id == "specific_target" for e in events)

    def test_get_forgetting_event_by_id(self, project):
        """get_forgetting_event returns a single event by ID."""
        event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_single",
            action="purge",
            reason="Test retrieval",
            backup_content=json.dumps({"text": "content"}),
        )

        retrieved = db.get_forgetting_event(event.id)
        assert retrieved is not None
        assert retrieved.id == event.id
        assert retrieved.action == "purge"
        assert retrieved.backup_content is not None

    def test_get_forgetting_event_returns_none_for_missing(self):
        """get_forgetting_event returns None for nonexistent ID."""
        result = db.get_forgetting_event("nonexistent-id")
        assert result is None

    def test_restore_marks_restored_at(self, project):
        """When a restore event is recorded, the original purge event can be
        marked with restored_at via mark_forgetting_event_restored."""
        # First purge
        purge_event = db.record_forgetting_event(
            project_id=project.id,
            target_type="lesson",
            target_id="mem_restore_test",
            action="purge",
            reason="Cleanup",
            backup_content=json.dumps({"text": "important content"}),
        )

        # Mark it as restored
        restored = db.mark_forgetting_event_restored(purge_event.id)
        assert restored is not None
        assert restored.restored_at is not None
        assert restored.can_restore is True  # Still has backup

    def test_get_forgetting_events_empty_for_no_events(self, project):
        """No events returns empty list."""
        events = db.get_forgetting_events(project_id=project.id)
        assert events == []
