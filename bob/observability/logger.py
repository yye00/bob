"""Structured logging for BOB framework.

Provides JSON-formatted logging with contextual information for events like
task execution, session management, and orchestration actions.
"""

import json
import logging
import logging.handlers
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class EventType(Enum):
    """Event types for structured logging."""

    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    ESCALATION_TRIGGERED = "escalation_triggered"
    RESEARCH_STARTED = "research_started"
    RESEARCH_COMPLETED = "research_completed"
    DECOMPOSITION_STARTED = "decomposition_started"
    DECOMPOSITION_COMPLETED = "decomposition_completed"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"


@dataclass
class LogContext:
    """Context information for structured logs."""

    project_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    model: Optional[str] = None
    agent_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Add event type if present
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type

        # Add context if present
        if hasattr(record, "context"):
            log_data["context"] = record.context

        # Add any extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class StructuredLogger:
    """Structured logger for BOB framework.

    Logs events with JSON formatting, context tracking, and rotation.
    """

    def __init__(
        self,
        name: str,
        log_dir: Optional[Path] = None,
        level: int = logging.INFO,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB
        backup_count: int = 5,
    ) -> None:
        """Initialize structured logger.

        Args:
            name: Logger name (typically module name)
            log_dir: Directory for log files (default: None, logs to console only)
            level: Logging level (default: INFO)
            max_bytes: Max bytes per log file before rotation (default: 10 MB)
            backup_count: Number of backup files to keep (default: 5)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False  # Don't propagate to root logger

        # Clear any existing handlers
        self.logger.handlers.clear()

        # Always add console handler for development
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(console_handler)

        # Add file handler if log directory specified
        if log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"{name}.log"
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setFormatter(JSONFormatter())
            self.logger.addHandler(file_handler)

        self.default_context = LogContext()

    def set_context(
        self,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> None:
        """Set default context for subsequent log events.

        Args:
            project_id: Project ID
            task_id: Task ID
            session_id: Session ID
            model: Model name
            agent_type: Agent type
        """
        if project_id is not None:
            self.default_context.project_id = project_id
        if task_id is not None:
            self.default_context.task_id = task_id
        if session_id is not None:
            self.default_context.session_id = session_id
        if model is not None:
            self.default_context.model = model
        if agent_type is not None:
            self.default_context.agent_type = agent_type

    def clear_context(self) -> None:
        """Clear the default context."""
        self.default_context = LogContext()

    def _log_event(
        self,
        level: int,
        message: str,
        event_type: Optional[EventType] = None,
        context: Optional[LogContext] = None,
        **extra: Any,
    ) -> None:
        """Log an event with structured data.

        Args:
            level: Log level
            message: Log message
            event_type: Type of event
            context: Additional context (merged with default)
            **extra: Additional fields to include
        """
        # Merge contexts
        merged_context = LogContext(
            project_id=context.project_id if context and context.project_id else self.default_context.project_id,
            task_id=context.task_id if context and context.task_id else self.default_context.task_id,
            session_id=context.session_id if context and context.session_id else self.default_context.session_id,
            model=context.model if context and context.model else self.default_context.model,
            agent_type=context.agent_type if context and context.agent_type else self.default_context.agent_type,
        )

        # Create log record with extra attributes
        record = self.logger.makeRecord(
            self.logger.name,
            level,
            "(structured)",
            0,
            message,
            (),
            None,
        )

        if event_type:
            record.event_type = event_type.value

        context_dict = merged_context.to_dict()
        if context_dict:
            record.context = context_dict

        if extra:
            record.extra_fields = extra

        self.logger.handle(record)

    def info(
        self,
        message: str,
        event_type: Optional[EventType] = None,
        context: Optional[LogContext] = None,
        **extra: Any,
    ) -> None:
        """Log info level message.

        Args:
            message: Log message
            event_type: Type of event
            context: Additional context
            **extra: Additional fields
        """
        self._log_event(logging.INFO, message, event_type, context, **extra)

    def warning(
        self,
        message: str,
        event_type: Optional[EventType] = None,
        context: Optional[LogContext] = None,
        **extra: Any,
    ) -> None:
        """Log warning level message.

        Args:
            message: Log message
            event_type: Type of event
            context: Additional context
            **extra: Additional fields
        """
        self._log_event(logging.WARNING, message, event_type, context, **extra)

    def error(
        self,
        message: str,
        event_type: Optional[EventType] = None,
        context: Optional[LogContext] = None,
        exc_info: bool = False,
        **extra: Any,
    ) -> None:
        """Log error level message.

        Args:
            message: Log message
            event_type: Type of event
            context: Additional context
            exc_info: Include exception info
            **extra: Additional fields
        """
        if exc_info:
            # Create record with exception info
            import sys
            record = self.logger.makeRecord(
                self.logger.name,
                logging.ERROR,
                "(structured)",
                0,
                message,
                (),
                sys.exc_info(),
            )
            if event_type:
                record.event_type = event_type.value

            merged_context = LogContext(
                project_id=context.project_id if context and context.project_id else self.default_context.project_id,
                task_id=context.task_id if context and context.task_id else self.default_context.task_id,
                session_id=context.session_id if context and context.session_id else self.default_context.session_id,
                model=context.model if context and context.model else self.default_context.model,
                agent_type=context.agent_type if context and context.agent_type else self.default_context.agent_type,
            )
            context_dict = merged_context.to_dict()
            if context_dict:
                record.context = context_dict

            if extra:
                record.extra_fields = extra

            self.logger.handle(record)
        else:
            self._log_event(logging.ERROR, message, event_type, context, **extra)

    def debug(
        self,
        message: str,
        event_type: Optional[EventType] = None,
        context: Optional[LogContext] = None,
        **extra: Any,
    ) -> None:
        """Log debug level message.

        Args:
            message: Log message
            event_type: Type of event
            context: Additional context
            **extra: Additional fields
        """
        self._log_event(logging.DEBUG, message, event_type, context, **extra)


def create_logger(
    name: str,
    project_workspace: Optional[Path] = None,
    level: int = logging.INFO,
) -> StructuredLogger:
    """Factory function to create a structured logger.

    Args:
        name: Logger name
        project_workspace: Project workspace directory (logs go to .bob/logs/)
        level: Logging level

    Returns:
        Configured StructuredLogger instance
    """
    log_dir = None
    if project_workspace:
        log_dir = Path(project_workspace) / ".bob" / "logs"

    return StructuredLogger(name, log_dir=log_dir, level=level)
