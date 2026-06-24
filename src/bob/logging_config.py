"""Structured Python logging configuration for Bob.

Provides a custom formatter that outputs logs in the format:
    [TIMESTAMP] [LEVEL] [COMPONENT] message

Example:
    [2026-02-12 17:00:00] [INFO] [orchestrator] Starting feature F001

Log levels:
    DEBUG:   Detailed execution info (sub-agent prompts, MCP calls)
    INFO:    Major events (feature start/complete, sub-agent spawn)
    WARNING: Recoverable issues (retry attempts, validation failures)
    ERROR:   Failures (feature failed, MCP error)
"""

import logging
import sys
from datetime import datetime

BOB_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(component)s] %(message)s"


class BobFormatter(logging.Formatter):
    """Custom formatter producing [TIMESTAMP] [LEVEL] [COMPONENT] message.

    The component is derived from the last segment of the dotted logger name.
    For example, "bob.orchestrator.claude_executor" yields "claude_executor".
    """

    def format(self, record: logging.LogRecord) -> str:
        # Extract component from logger name (last dotted segment)
        name_parts = record.name.rsplit(".", 1)
        record.component = name_parts[-1] if name_parts else record.name

        # Format timestamp as YYYY-MM-DD HH:MM:SS
        record.asctime = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        return f"[{record.asctime}] [{record.levelname}] [{record.component}] {record.getMessage()}"


class _StderrHandler(logging.StreamHandler):
    """StreamHandler that always resolves sys.stderr at emit time.

    Unlike the default StreamHandler which captures a reference to the stream
    at construction time, this handler resolves sys.stderr fresh on every emit.
    This prevents stale-stream issues when stderr is replaced (e.g., by Click's
    CliRunner during testing).
    """

    def __init__(self) -> None:
        # Initialize with current stderr; emit() overrides it
        super().__init__(sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


def setup_logging(*, verbose: bool = False, level: int | None = None) -> None:
    """Configure the bob logger with structured output to stderr.

    Logs go to stderr to avoid interfering with CLI command output on stdout.

    Args:
        verbose: If True, set log level to DEBUG. Otherwise INFO.
        level: Explicit log level override. Takes precedence over verbose.
    """
    logger = logging.getLogger("bob")

    if level is not None:
        log_level = level
    elif verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logger.setLevel(log_level)

    # Avoid adding duplicate handlers on repeated calls
    if not any(isinstance(h, _StderrHandler) for h in logger.handlers):
        handler = _StderrHandler()
        handler.setFormatter(BobFormatter())
        logger.addHandler(handler)
