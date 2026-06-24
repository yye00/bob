"""Tests for F065: Implement execution logging to execution_logs table.

Validates that:
- Step 1: log_event() function exists and creates log entries
- Step 2: Supports levels: debug, info, warning, error
- Step 3: Links to sub_agent_run_id if applicable
- Step 4: Log events at different levels, verify storage
"""

import pathlib

import pytest

from bob import db
from bob.models import ExecutionLog

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project."""
    return db.create_project(
        name="F065 Test Project",
        workspace_path="/tmp/test-f065",
    )


@pytest.fixture()
def agent_run(project):
    """Create a test sub-agent run."""
    return db.create_agent_run(
        project_id=project.id,
        purpose="test_execution",
        target_type="feature",
        target_id="F065",
    )


# ===================================================================
# Step 1: log_event() function exists and creates log entries
# ===================================================================


class TestLogEventExists:
    """Step 1: log_event() must exist and create execution_logs rows."""

    def test_function_exists(self):
        assert hasattr(db, "log_event")
        assert callable(db.log_event)

    def test_creates_log_entry(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Feature build started",
        )
        assert isinstance(log, ExecutionLog)
        assert log.project_id == project.id
        assert log.event == "Feature build started"

    def test_returns_log_with_id(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Test event",
        )
        assert log.id is not None
        assert len(log.id) > 0

    def test_default_level_is_info(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Default level event",
        )
        assert log.level == "info"

    def test_stores_details(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Event with details",
            details='{"key": "value"}',
        )
        assert log.details == '{"key": "value"}'

    def test_persisted_to_database(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Persisted event",
        )
        retrieved = db.get_execution_log(log.id)
        assert retrieved is not None
        assert retrieved.id == log.id
        assert retrieved.event == "Persisted event"

    def test_has_created_at_timestamp(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Timestamped event",
        )
        assert log.created_at is not None


# ===================================================================
# Step 2: Supports levels: debug, info, warning, error
# ===================================================================


class TestLogLevels:
    """Step 2: log_event() must support debug, info, warning, error levels."""

    def test_debug_level(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Debug message",
            level="debug",
        )
        assert log.level == "debug"

    def test_info_level(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Info message",
            level="info",
        )
        assert log.level == "info"

    def test_warning_level(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Warning message",
            level="warning",
        )
        assert log.level == "warning"

    def test_error_level(self, project):
        log = db.log_event(
            project_id=project.id,
            event="Error message",
            level="error",
        )
        assert log.level == "error"

    def test_invalid_level_raises_error(self, project):
        with pytest.raises(ValueError, match="Invalid log level"):
            db.log_event(
                project_id=project.id,
                event="Bad level",
                level="critical",
            )

    def test_all_levels_persisted(self, project):
        """All four levels should be retrievable from the database."""
        for level in ("debug", "info", "warning", "error"):
            log = db.log_event(
                project_id=project.id,
                event=f"{level} event",
                level=level,
            )
            retrieved = db.get_execution_log(log.id)
            assert retrieved is not None
            assert retrieved.level == level


# ===================================================================
# Step 3: Link to sub_agent_run_id if applicable
# ===================================================================


class TestSubAgentRunLink:
    """Step 3: log_event() can link to a sub_agent_run_id."""

    def test_link_to_agent_run(self, project, agent_run):
        log = db.log_event(
            project_id=project.id,
            event="Agent started task",
            sub_agent_run_id=agent_run.id,
        )
        assert log.sub_agent_run_id == agent_run.id

    def test_no_agent_run_link(self, project):
        log = db.log_event(
            project_id=project.id,
            event="System event",
        )
        assert log.sub_agent_run_id is None

    def test_agent_run_link_persisted(self, project, agent_run):
        log = db.log_event(
            project_id=project.id,
            event="Linked event",
            sub_agent_run_id=agent_run.id,
        )
        retrieved = db.get_execution_log(log.id)
        assert retrieved is not None
        assert retrieved.sub_agent_run_id == agent_run.id

    def test_query_by_agent_run(self, project, agent_run):
        """query_execution_logs can filter by sub_agent_run_id."""
        db.log_event(
            project_id=project.id,
            event="Agent event 1",
            sub_agent_run_id=agent_run.id,
        )
        db.log_event(
            project_id=project.id,
            event="System event",
        )
        db.log_event(
            project_id=project.id,
            event="Agent event 2",
            sub_agent_run_id=agent_run.id,
        )

        logs = db.query_execution_logs(
            project_id=project.id,
            sub_agent_run_id=agent_run.id,
        )
        assert len(logs) == 2
        assert all(l.sub_agent_run_id == agent_run.id for l in logs)


# ===================================================================
# Step 4: Log events at different levels, verify storage
# ===================================================================


class TestLogStorageIntegration:
    """Step 4: Full integration test - log at different levels, verify storage."""

    def test_multiple_levels_stored_and_retrievable(self, project):
        """Log events at all four levels, then query and verify each is stored."""
        events = [
            ("debug", "Entering function parse_config"),
            ("info", "Feature F065 build started"),
            ("warning", "Approaching resource limit (80% used)"),
            ("error", "Sub-agent crashed: timeout after 300s"),
        ]

        created_ids = []
        for level, event in events:
            log = db.log_event(
                project_id=project.id,
                event=event,
                level=level,
            )
            created_ids.append(log.id)

        # Verify all 4 events are stored
        all_logs = db.query_execution_logs(project_id=project.id)
        assert len(all_logs) == 4

        # Verify each level can be filtered
        for level, event in events:
            filtered = db.query_execution_logs(
                project_id=project.id,
                level=level,
            )
            assert len(filtered) == 1
            assert filtered[0].event == event
            assert filtered[0].level == level

    def test_query_returns_newest_first(self, project):
        """Logs should be returned in descending created_at order."""
        db.log_event(project_id=project.id, event="First")
        db.log_event(project_id=project.id, event="Second")
        db.log_event(project_id=project.id, event="Third")

        logs = db.query_execution_logs(project_id=project.id)
        assert logs[0].event == "Third"
        assert logs[2].event == "First"

    def test_query_with_limit(self, project):
        """query_execution_logs respects limit parameter."""
        for i in range(5):
            db.log_event(project_id=project.id, event=f"Event {i}")

        logs = db.query_execution_logs(project_id=project.id, limit=3)
        assert len(logs) == 3

    def test_get_nonexistent_log_returns_none(self):
        result = db.get_execution_log("nonexistent-id")
        assert result is None

    def test_mixed_levels_with_agent_run(self, project, agent_run):
        """Log events with different levels, some linked to agent runs."""
        db.log_event(
            project_id=project.id,
            event="Agent starting",
            level="info",
            sub_agent_run_id=agent_run.id,
        )
        db.log_event(
            project_id=project.id,
            event="Retrying failed operation",
            level="warning",
            sub_agent_run_id=agent_run.id,
        )
        db.log_event(
            project_id=project.id,
            event="System checkpoint",
            level="debug",
        )
        db.log_event(
            project_id=project.id,
            event="Agent failed",
            level="error",
            sub_agent_run_id=agent_run.id,
        )

        # Query all for project
        all_logs = db.query_execution_logs(project_id=project.id)
        assert len(all_logs) == 4

        # Query only agent-linked logs
        agent_logs = db.query_execution_logs(
            project_id=project.id,
            sub_agent_run_id=agent_run.id,
        )
        assert len(agent_logs) == 3

        # Query only errors
        error_logs = db.query_execution_logs(
            project_id=project.id,
            level="error",
        )
        assert len(error_logs) == 1
        assert error_logs[0].event == "Agent failed"

    def test_details_stored_and_retrieved(self, project):
        """Details field should be stored and retrievable."""
        log = db.log_event(
            project_id=project.id,
            event="Complex event",
            level="info",
            details='{"tokens_used": 1500, "duration_ms": 3200}',
        )

        retrieved = db.get_execution_log(log.id)
        assert retrieved is not None
        assert retrieved.details == '{"tokens_used": 1500, "duration_ms": 3200}'
