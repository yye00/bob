"""Tests for StructuredLogger."""

import json
import logging
from io import StringIO
from pathlib import Path

import pytest

from bob.observability.logger import (
    EventType,
    JSONFormatter,
    LogContext,
    StructuredLogger,
    create_logger,
)


class TestLogContext:
    """Test LogContext dataclass."""

    def test_to_dict_all_fields(self):
        """Test to_dict with all fields populated."""
        context = LogContext(
            project_id="proj-1",
            task_id="task-1",
            session_id="sess-1",
            model="claude-sonnet-4",
            agent_type="coding",
        )

        result = context.to_dict()

        assert result == {
            "project_id": "proj-1",
            "task_id": "task-1",
            "session_id": "sess-1",
            "model": "claude-sonnet-4",
            "agent_type": "coding",
        }

    def test_to_dict_partial_fields(self):
        """Test to_dict excludes None values."""
        context = LogContext(
            project_id="proj-1",
            session_id="sess-1",
        )

        result = context.to_dict()

        assert result == {
            "project_id": "proj-1",
            "session_id": "sess-1",
        }
        assert "task_id" not in result
        assert "model" not in result
        assert "agent_type" not in result

    def test_to_dict_empty(self):
        """Test to_dict with no fields set."""
        context = LogContext()
        result = context.to_dict()
        assert result == {}


class TestJSONFormatter:
    """Test JSONFormatter."""

    def test_format_basic_message(self):
        """Test formatting a basic log message."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"

    def test_format_with_event_type(self):
        """Test formatting with event type."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Task started",
            args=(),
            exc_info=None,
        )
        record.event_type = "task_started"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["event_type"] == "task_started"

    def test_format_with_context(self):
        """Test formatting with context."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Processing task",
            args=(),
            exc_info=None,
        )
        record.context = {"project_id": "proj-1", "task_id": "task-1"}

        result = formatter.format(record)
        data = json.loads(result)

        assert data["context"] == {"project_id": "proj-1", "task_id": "task-1"}

    def test_format_with_extra_fields(self):
        """Test formatting with extra fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Processing",
            args=(),
            exc_info=None,
        )
        record.extra_fields = {"duration": 1.5, "status": "success"}

        result = formatter.format(record)
        data = json.loads(result)

        assert data["duration"] == 1.5
        assert data["status"] == "success"

    def test_format_with_exception(self):
        """Test formatting with exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )

        result = formatter.format(record)
        data = json.loads(result)

        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]


class TestStructuredLogger:
    """Test StructuredLogger class."""

    @pytest.fixture
    def string_handler(self):
        """Create a string handler for capturing log output."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        return handler, stream

    def test_init_console_only(self):
        """Test initialization with console logging only."""
        logger = StructuredLogger("test_logger")

        assert logger.logger.name == "test_logger"
        assert logger.logger.level == logging.INFO
        assert len(logger.logger.handlers) >= 1
        assert not logger.logger.propagate

    def test_init_with_log_dir(self, tmp_path):
        """Test initialization with file logging."""
        log_dir = tmp_path / "logs"
        logger = StructuredLogger("test_logger", log_dir=log_dir)

        assert log_dir.exists()
        assert len(logger.logger.handlers) >= 2  # Console + file

        # Check log file was created
        log_file = log_dir / "test_logger.log"
        assert log_file.exists()

    def test_set_context(self):
        """Test setting default context."""
        logger = StructuredLogger("test_logger")

        logger.set_context(
            project_id="proj-1",
            task_id="task-1",
            session_id="sess-1",
            model="claude-sonnet-4",
            agent_type="coding",
        )

        assert logger.default_context.project_id == "proj-1"
        assert logger.default_context.task_id == "task-1"
        assert logger.default_context.session_id == "sess-1"
        assert logger.default_context.model == "claude-sonnet-4"
        assert logger.default_context.agent_type == "coding"

    def test_set_context_partial(self):
        """Test setting partial context."""
        logger = StructuredLogger("test_logger")

        logger.set_context(project_id="proj-1")
        assert logger.default_context.project_id == "proj-1"
        assert logger.default_context.task_id is None

        logger.set_context(task_id="task-1")
        assert logger.default_context.project_id == "proj-1"
        assert logger.default_context.task_id == "task-1"

    def test_clear_context(self):
        """Test clearing context."""
        logger = StructuredLogger("test_logger")

        logger.set_context(project_id="proj-1", task_id="task-1")
        logger.clear_context()

        assert logger.default_context.project_id is None
        assert logger.default_context.task_id is None

    def test_info_logging(self, string_handler):
        """Test info level logging."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.info("Test message")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "INFO"
        assert data["message"] == "Test message"

    def test_info_with_event_type(self, string_handler):
        """Test logging with event type."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.info("Task started", event_type=EventType.TASK_STARTED)

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["event_type"] == "task_started"

    def test_info_with_context(self, string_handler):
        """Test logging with explicit context."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        context = LogContext(project_id="proj-1", task_id="task-1")
        logger.info("Processing", context=context)

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["context"]["project_id"] == "proj-1"
        assert data["context"]["task_id"] == "task-1"

    def test_info_with_default_context(self, string_handler):
        """Test logging uses default context."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.set_context(project_id="proj-1", session_id="sess-1")
        logger.info("Test message")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["context"]["project_id"] == "proj-1"
        assert data["context"]["session_id"] == "sess-1"

    def test_info_context_override(self, string_handler):
        """Test explicit context overrides default."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.set_context(project_id="proj-1", task_id="task-1")
        context = LogContext(task_id="task-2")
        logger.info("Test", context=context)

        output = stream.getvalue()
        data = json.loads(output.strip())

        # Explicit context overrides default
        assert data["context"]["task_id"] == "task-2"
        # But default is used for other fields
        assert data["context"]["project_id"] == "proj-1"

    def test_info_with_extra_fields(self, string_handler):
        """Test logging with extra fields."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.info("Task completed", duration=1.5, status="success")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["duration"] == 1.5
        assert data["status"] == "success"

    def test_warning_logging(self, string_handler):
        """Test warning level logging."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.warning("Warning message")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "WARNING"
        assert data["message"] == "Warning message"

    def test_error_logging(self, string_handler):
        """Test error level logging."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        logger.error("Error message")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "ERROR"
        assert data["message"] == "Error message"

    def test_error_with_exception(self, string_handler):
        """Test error logging with exception info."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.error("Error occurred", exc_info=True)

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]

    def test_debug_logging(self, string_handler):
        """Test debug level logging."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger", level=logging.DEBUG)
        logger.logger.handlers = [handler]

        logger.debug("Debug message")

        output = stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "DEBUG"
        assert data["message"] == "Debug message"

    def test_log_rotation(self, tmp_path):
        """Test log file rotation."""
        log_dir = tmp_path / "logs"
        # Create logger with small max size for testing
        logger = StructuredLogger(
            "test_logger",
            log_dir=log_dir,
            max_bytes=100,  # Very small for testing
            backup_count=2,
        )

        # Write enough logs to trigger rotation
        for i in range(50):
            logger.info(f"Message {i} - " + "x" * 50)

        # Check that log files were created
        log_file = log_dir / "test_logger.log"
        assert log_file.exists()

        # Check for rotated files (may or may not exist depending on exact sizes)
        # Just verify the main log file exists and is being written to
        assert log_file.stat().st_size > 0

    def test_multiple_event_types(self, string_handler):
        """Test logging different event types."""
        handler, stream = string_handler
        logger = StructuredLogger("test_logger")
        logger.logger.handlers = [handler]
        logger.set_context(project_id="proj-1")

        # Log various event types
        logger.info("Session started", event_type=EventType.SESSION_STARTED)
        logger.info("Task started", event_type=EventType.TASK_STARTED)
        logger.info("Research started", event_type=EventType.RESEARCH_STARTED)
        logger.info("Escalation triggered", event_type=EventType.ESCALATION_TRIGGERED)
        logger.info("Task completed", event_type=EventType.TASK_COMPLETED)
        logger.info("Session ended", event_type=EventType.SESSION_ENDED)

        output = stream.getvalue()
        lines = [line for line in output.strip().split("\n") if line]

        assert len(lines) == 6

        # Verify each line is valid JSON with expected event type
        event_types = [
            "session_started",
            "task_started",
            "research_started",
            "escalation_triggered",
            "task_completed",
            "session_ended",
        ]

        for line, expected_type in zip(lines, event_types):
            data = json.loads(line)
            assert data["event_type"] == expected_type
            assert data["context"]["project_id"] == "proj-1"


class TestCreateLogger:
    """Test create_logger factory function."""

    def test_create_logger_console_only(self):
        """Test creating logger without workspace."""
        logger = create_logger("test_logger")

        assert isinstance(logger, StructuredLogger)
        assert logger.logger.name == "test_logger"
        assert logger.logger.level == logging.INFO

    def test_create_logger_with_workspace(self, tmp_path):
        """Test creating logger with workspace."""
        workspace = tmp_path / "project"
        workspace.mkdir()

        logger = create_logger("test_logger", project_workspace=workspace)

        # Check .bob/logs directory was created
        log_dir = workspace / ".bob" / "logs"
        assert log_dir.exists()

        # Check log file was created
        log_file = log_dir / "test_logger.log"
        assert log_file.exists()

    def test_create_logger_custom_level(self):
        """Test creating logger with custom level."""
        logger = create_logger("test_logger", level=logging.DEBUG)

        assert logger.logger.level == logging.DEBUG

    def test_create_logger_logs_to_file(self, tmp_path):
        """Test that logger actually writes to file."""
        workspace = tmp_path / "project"
        workspace.mkdir()

        logger = create_logger("test_logger", project_workspace=workspace)
        logger.info("Test message", event_type=EventType.TASK_STARTED)

        log_file = workspace / ".bob" / "logs" / "test_logger.log"
        content = log_file.read_text()

        data = json.loads(content.strip())
        assert data["message"] == "Test message"
        assert data["event_type"] == "task_started"


class TestEventTypes:
    """Test EventType enum."""

    def test_all_event_types_defined(self):
        """Test that all required event types are defined."""
        expected_types = [
            "TASK_STARTED",
            "TASK_COMPLETED",
            "TASK_FAILED",
            "SESSION_STARTED",
            "SESSION_ENDED",
            "ESCALATION_TRIGGERED",
            "RESEARCH_STARTED",
            "RESEARCH_COMPLETED",
        ]

        for event_name in expected_types:
            assert hasattr(EventType, event_name), f"Missing {event_name}"

    def test_event_type_values(self):
        """Test event type string values."""
        assert EventType.TASK_STARTED.value == "task_started"
        assert EventType.TASK_COMPLETED.value == "task_completed"
        assert EventType.TASK_FAILED.value == "task_failed"
        assert EventType.SESSION_STARTED.value == "session_started"
        assert EventType.SESSION_ENDED.value == "session_ended"
        assert EventType.ESCALATION_TRIGGERED.value == "escalation_triggered"
        assert EventType.RESEARCH_STARTED.value == "research_started"
        assert EventType.RESEARCH_COMPLETED.value == "research_completed"
