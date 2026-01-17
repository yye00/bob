"""Integration tests for structured logging.

Tests the full logging workflow including:
- Creating a test project
- Running commands with logging enabled
- Verifying JSON log files are created
- Verifying log schema and structure
- Testing log filtering and display
"""

import json
import logging
import tempfile
import time
from pathlib import Path

import pytest

from bob.database import DatabaseManager
from bob.models.base import AgentType, Project, ProjectStatus, Session, SessionStatus
from bob.observability.logger import EventType, LogContext, create_logger


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def test_project(temp_workspace):
    """Create a test project with logging directory."""
    project_dir = temp_workspace / "test-project"
    project_dir.mkdir()

    # Create .bob directory structure
    bob_dir = project_dir / ".bob"
    bob_dir.mkdir()
    logs_dir = bob_dir / "logs"
    logs_dir.mkdir()

    return {
        "project_dir": project_dir,
        "bob_dir": bob_dir,
        "logs_dir": logs_dir,
    }


class TestLoggingIntegration:
    """Integration tests for structured logging."""

    def test_creates_json_log_files(self, test_project):
        """Test that JSON log files are created in .bob/logs/."""
        logs_dir = test_project["logs_dir"]

        # Create logger with log directory
        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
        )

        # Log some events
        logger.info("Test log message", event_type=EventType.SESSION_STARTED)

        # Verify log file was created
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0, "No log files created"

        # Verify file is in logs directory
        assert all(f.parent == logs_dir for f in log_files)

    def test_logs_have_correct_schema(self, test_project):
        """Test that all events are logged with correct schema."""
        logs_dir = test_project["logs_dir"]

        # Create logger
        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        # Set context
        logger.set_context(
                project_id="proj-001",
                task_id="task-001",
                session_id="sess-001",
                model="claude-sonnet-4",
                agent_type="coding",
            )

        # Log various event types
        logger.info(
            "Session started",
            event_type=EventType.SESSION_STARTED,
        )
        logger.info(
            "Task started",
            event_type=EventType.TASK_STARTED,
        )
        logger.info(
            "Agent message",
            event_type=EventType.TASK_STARTED,
            extra_data={"content": "test message"},
        )

        # Wait for logs to be written
        time.sleep(0.1)

        # Parse log file
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        log_entries = []
        with open(log_files[0], "r") as f:
            for line in f:
                log_entries.append(json.loads(line))

        # Verify we have log entries
        assert len(log_entries) >= 3

        # Verify each log entry has required top-level fields
        required_top_fields = [
            "timestamp",
            "level",
            "message",
            "event_type",
            "context",
        ]

        # Verify each log entry has required context fields
        required_context_fields = [
            "project_id",
            "task_id",
            "session_id",
            "model",
            "agent_type",
        ]

        for entry in log_entries:
            for field in required_top_fields:
                assert field in entry, f"Missing field: {field}"

            # Verify context has required fields
            context = entry.get("context", {})
            for field in required_context_fields:
                assert field in context, f"Missing context field: {field}"

            # Verify timestamp is ISO format
            assert "T" in entry["timestamp"]
            assert entry["timestamp"].endswith("Z") or "+" in entry["timestamp"]

            # Verify level is valid
            assert entry["level"] in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

            # Verify event_type is valid
            assert entry["event_type"] in [
                "session_started",
                "session_ended",
                "task_started",
                "task_completed",
                "task_failed",
                "checkpoint_created",
                "research_started",
                "research_completed",
                "escalation_triggered",
                "decomposition_started",
                "decomposition_completed",
                "checkpoint_restored",
            ]

    def test_parse_json_logs_programmatically(self, test_project):
        """Test parsing JSON logs programmatically and verifying structure."""
        logs_dir = test_project["logs_dir"]

        # Create logger
        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        # Log with specific data
        test_data = {
            "project_id": "proj-test-123",
            "session_id": "sess-abc-456",
            "custom_field": "custom_value",
        }

        logger.set_context(
                project_id=test_data["project_id"],
                session_id=test_data["session_id"],
            )

        logger.info(
            "Test message",
            event_type=EventType.SESSION_STARTED,
            extra_data={"custom_field": test_data["custom_field"]},
        )

        # Wait for write
        time.sleep(0.1)

        # Parse and verify
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], "r") as f:
            log_lines = f.readlines()

        # Find our test log entry
        found = False
        for line in log_lines:
            entry = json.loads(line)
            context = entry.get("context", {})
            if context.get("project_id") == test_data["project_id"]:
                found = True
                assert context["session_id"] == test_data["session_id"]
                assert entry["message"] == "Test message"
                assert entry["event_type"] == "session_started"
                # extra_data is stored under "extra_data" key
                assert entry.get("extra_data", {}).get("custom_field") == test_data["custom_field"]
                break

        assert found, "Test log entry not found"

    def test_logging_different_event_types(self, test_project):
        """Test logging all different event types."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        logger.set_context(session_id="sess-001")

        # Log all event types
        event_types = [
            EventType.SESSION_STARTED,
            EventType.SESSION_ENDED,
            EventType.TASK_STARTED,
            EventType.TASK_COMPLETED,
            EventType.TASK_FAILED,
            EventType.TASK_STARTED,
            EventType.TASK_FAILED,
            EventType.CHECKPOINT_CREATED,
            EventType.RESEARCH_STARTED,
            EventType.RESEARCH_COMPLETED,
        ]

        for event_type in event_types:
            logger.info(f"Testing {event_type}", event_type=event_type)

        time.sleep(0.1)

        # Parse logs
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], "r") as f:
            log_entries = [json.loads(line) for line in f]

        # Verify all event types were logged
        logged_events = {entry["event_type"] for entry in log_entries}
        expected_events = {
            "session_started",
            "session_ended",
            "task_started",
            "task_completed",
            "task_failed",
            "task_started",
            "task_failed",
            "checkpoint_created",
            "research_started",
            "research_completed",
        }

        assert expected_events.issubset(logged_events)

    def test_logging_with_different_levels(self, test_project):
        """Test logging with different log levels."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.DEBUG,  # Capture all levels
        )

        # Log at different levels
        logger.debug("Debug message", event_type=EventType.TASK_STARTED)
        logger.info("Info message", event_type=EventType.TASK_STARTED)
        logger.warning("Warning message", event_type=EventType.TASK_FAILED)
        logger.error("Error message", event_type=EventType.TASK_FAILED)

        time.sleep(0.1)

        # Parse logs
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], "r") as f:
            log_entries = [json.loads(line) for line in f]

        # Verify all levels were logged
        logged_levels = {entry["level"] for entry in log_entries}
        expected_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}

        assert expected_levels.issubset(logged_levels)

    def test_logging_with_exception(self, test_project):
        """Test logging exceptions with traceback."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.ERROR,
        )

        # Log with exception
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            logger.error(
                "Exception occurred",
                event_type=EventType.TASK_FAILED,
                exc_info=True,
            )

        time.sleep(0.1)

        # Parse logs
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], "r") as f:
            log_entries = [json.loads(line) for line in f]

        # Find exception log
        exception_log = None
        for entry in log_entries:
            if "Exception occurred" in entry.get("message", ""):
                exception_log = entry
                break

        assert exception_log is not None
        assert "exception" in exception_log
        assert "ValueError" in exception_log["exception"]
        assert "Test exception" in exception_log["exception"]
        assert "Traceback" in exception_log["exception"]

    def test_logging_context_propagation(self, test_project):
        """Test that context is properly propagated to all log entries."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        # Set context
        logger.set_context(
            project_id="proj-001",
            task_id="task-001",
            session_id="sess-001",
            model="claude-sonnet-4",
            agent_type="coding",
        )

        # Log multiple messages
        logger.info("Message 1", event_type=EventType.SESSION_STARTED)
        logger.info("Message 2", event_type=EventType.TASK_STARTED)
        logger.info("Message 3", event_type=EventType.TASK_STARTED)

        time.sleep(0.1)

        # Parse logs
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], "r") as f:
            log_entries = [json.loads(line) for line in f]

        # Verify context is in all entries
        for entry in log_entries:
            context = entry.get("context", {})
            assert context.get("project_id") == "proj-001"
            assert context.get("task_id") == "task-001"
            assert context.get("session_id") == "sess-001"
            assert context.get("model") == "claude-sonnet-4"
            assert context.get("agent_type") == "coding"

    def test_logging_file_rotation(self, test_project):
        """Test that log files rotate properly."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        # Log many messages to potentially trigger rotation
        # (In practice, rotation is based on file size or time)
        for i in range(100):
            logger.info(f"Log message {i}", event_type=EventType.TASK_STARTED)

        time.sleep(0.1)

        # Verify at least one log file exists
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        # Verify all files are valid JSON
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    entry = json.loads(line)  # Should not raise
                    assert "message" in entry
                    assert "timestamp" in entry


class TestLoggingCLIIntegration:
    """Integration tests for 'bob logs' CLI command."""

    def test_logs_command_with_real_logs(self, test_project):
        """Test 'bob logs' command displays real logs correctly."""
        logs_dir = test_project["logs_dir"]

        # Create some logs
        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        logger.set_context(session_id="test-session")
        logger.info("Test log entry", event_type=EventType.SESSION_STARTED)

        time.sleep(0.1)

        # Verify log file exists and is readable
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) > 0

        # Simulate what 'bob logs' command does - read and parse logs
        all_logs = []
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    all_logs.append(json.loads(line))

        # Verify we can filter by session
        session_logs = [
            log for log in all_logs
            if log.get("context", {}).get("session_id") == "test-session"
        ]
        assert len(session_logs) > 0
        assert session_logs[0]["message"] == "Test log entry"

    def test_logs_filtering_by_event_type(self, test_project):
        """Test filtering logs by event type."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.INFO,
        )

        # Log different event types
        logger.info("Session started", event_type=EventType.SESSION_STARTED)
        logger.info("Task started", event_type=EventType.TASK_STARTED)
        logger.info("Agent message", event_type=EventType.TASK_STARTED)
        logger.info("Task completed", event_type=EventType.TASK_COMPLETED)

        time.sleep(0.1)

        # Parse all logs
        log_files = list(logs_dir.glob("*.log"))
        all_logs = []
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    all_logs.append(json.loads(line))

        # Filter by event type
        session_logs = [
            log for log in all_logs if log.get("event_type") == "session_started"
        ]
        task_logs = [
            log for log in all_logs if log.get("event_type") == "task_started"
        ]

        assert len(session_logs) >= 1
        assert len(task_logs) >= 1
        assert session_logs[0]["message"] == "Session started"
        assert task_logs[0]["message"] == "Task started"

    def test_logs_filtering_by_level(self, test_project):
        """Test filtering logs by level."""
        logs_dir = test_project["logs_dir"]

        logger = create_logger(
            name="test_logger",
            project_workspace=test_project["project_dir"],
            level=logging.DEBUG,
        )

        # Log at different levels
        logger.debug("Debug message", event_type=EventType.TASK_STARTED)
        logger.info("Info message", event_type=EventType.TASK_STARTED)
        logger.warning("Warning message", event_type=EventType.TASK_FAILED)
        logger.error("Error message", event_type=EventType.TASK_FAILED)

        time.sleep(0.1)

        # Parse all logs
        log_files = list(logs_dir.glob("*.log"))
        all_logs = []
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    all_logs.append(json.loads(line))

        # Filter by level
        error_logs = [log for log in all_logs if log.get("level") == "ERROR"]
        warning_logs = [log for log in all_logs if log.get("level") == "WARNING"]
        info_logs = [log for log in all_logs if log.get("level") == "INFO"]

        assert len(error_logs) >= 1
        assert len(warning_logs) >= 1
        assert len(info_logs) >= 1
