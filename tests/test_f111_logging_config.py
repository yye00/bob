"""Tests for F111: Python Logging Integration.

Verifies:
- logging_config module creates the expected structured formatter
- Default log level is INFO
- setup_logging configures the root bob logger to stdout
- Verbose mode sets level to DEBUG
- Log format matches: [TIMESTAMP] [LEVEL] [COMPONENT] message
- Logging integration in CLI, orchestrator, and MCP modules
"""

import logging
import re
from io import StringIO
from unittest.mock import patch

import pytest

from bob.logging_config import BOB_LOG_FORMAT, setup_logging, BobFormatter


class TestBobFormatter:
    """Test the custom Bob structured log formatter."""

    def test_format_matches_spec(self):
        """Log output matches [TIMESTAMP] [LEVEL] [COMPONENT] message."""
        formatter = BobFormatter()
        record = logging.LogRecord(
            name="bob.orchestrator",
            level=logging.INFO,
            pathname="orchestrator.py",
            lineno=42,
            msg="Starting feature F001",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        # Pattern: [YYYY-MM-DD HH:MM:SS] [INFO] [orchestrator] Starting feature F001
        pattern = r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[INFO\] \[orchestrator\] Starting feature F001$"
        assert re.match(pattern, output), f"Log output does not match expected format: {output!r}"

    def test_format_extracts_component_from_name(self):
        """Component is the last part of the dotted logger name."""
        formatter = BobFormatter()
        record = logging.LogRecord(
            name="bob.orchestrator.claude_executor",
            level=logging.DEBUG,
            pathname="claude_executor.py",
            lineno=10,
            msg="Spawning sub-agent",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[claude_executor]" in output

    def test_format_uses_full_name_for_short_logger(self):
        """When the logger name has no dots, use the full name as component."""
        formatter = BobFormatter()
        record = logging.LogRecord(
            name="bob",
            level=logging.WARNING,
            pathname="__init__.py",
            lineno=1,
            msg="A warning",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[bob]" in output
        assert "[WARNING]" in output

    def test_format_all_levels(self):
        """All standard log levels produce correct level strings."""
        formatter = BobFormatter()
        for level_name, level in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]:
            record = logging.LogRecord(
                name="bob.test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg="test message",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            assert f"[{level_name}]" in output


class TestSetupLogging:
    """Test the setup_logging function."""

    def teardown_method(self):
        """Clean up bob logger handlers after each test."""
        logger = logging.getLogger("bob")
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)

    def test_default_level_is_info(self):
        """Default log level is INFO."""
        setup_logging()
        logger = logging.getLogger("bob")
        assert logger.level == logging.INFO

    def test_verbose_sets_debug(self):
        """Passing verbose=True sets log level to DEBUG."""
        setup_logging(verbose=True)
        logger = logging.getLogger("bob")
        assert logger.level == logging.DEBUG

    def test_adds_stdout_handler(self):
        """setup_logging adds a StreamHandler to the bob logger."""
        setup_logging()
        logger = logging.getLogger("bob")
        assert len(logger.handlers) >= 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)

    def test_handler_uses_bob_formatter(self):
        """The handler uses BobFormatter."""
        setup_logging()
        logger = logging.getLogger("bob")
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, BobFormatter)

    def test_does_not_add_duplicate_handlers(self):
        """Calling setup_logging twice does not duplicate handlers."""
        setup_logging()
        setup_logging()
        logger = logging.getLogger("bob")
        assert len(logger.handlers) == 1

    def test_child_loggers_inherit_config(self):
        """Child loggers (bob.cli, bob.orchestrator) inherit the setup."""
        setup_logging()
        child = logging.getLogger("bob.orchestrator")
        # Child should have effective level of INFO (inherited from parent)
        assert child.getEffectiveLevel() == logging.INFO

    def test_output_goes_to_stderr(self, capsys):
        """Verify log output reaches stderr (to avoid mixing with CLI output)."""
        setup_logging()
        logger = logging.getLogger("bob.test_module")
        logger.info("Test message for stderr")
        captured = capsys.readouterr()
        assert "Test message for stderr" in captured.err

    def test_custom_level_parameter(self):
        """setup_logging accepts a level parameter."""
        setup_logging(level=logging.WARNING)
        logger = logging.getLogger("bob")
        assert logger.level == logging.WARNING


class TestLoggingIntegration:
    """Test that logging is integrated into existing modules."""

    def test_cli_module_has_logger(self):
        """CLI module should use logging."""
        from bob import cli
        assert hasattr(cli, "logger")
        assert cli.logger.name == "bob.cli"

    def test_claude_executor_has_logger(self):
        """Claude executor already has a logger."""
        from bob.orchestrator import claude_executor
        assert hasattr(claude_executor, "logger")
        assert claude_executor.logger.name == "bob.orchestrator.claude_executor"

    def test_mcp_lifecycle_has_logger(self):
        """MCP lifecycle already has a logger."""
        from bob import mcp_lifecycle
        assert hasattr(mcp_lifecycle, "logger")
        assert mcp_lifecycle.logger.name == "bob.mcp_lifecycle"

    def test_db_module_has_logger(self):
        """DB module should use logging."""
        from bob import db
        assert hasattr(db, "logger")
        assert db.logger.name == "bob.db"


class TestBobLogFormat:
    """Test the BOB_LOG_FORMAT constant."""

    def test_format_string_defined(self):
        """BOB_LOG_FORMAT should be a non-empty string."""
        assert isinstance(BOB_LOG_FORMAT, str)
        assert len(BOB_LOG_FORMAT) > 0
