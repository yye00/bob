"""Concurrent feature dispatch slot management for the Bob orchestrator.

Feature: Orchestrator dispatch concurrency — let multiple ready features run
in parallel instead of strict single-flight.

This module provides:
- :class:`ConcurrentDispatchSlot`: tracks a single in-flight feature dispatch
- Re-exports :func:`dispatch_concurrent_features` from
  :mod:`bob.orchestrator.run_loop` for backward-compatible access

The orchestrator tick loop can use these to maintain a pool of up to
``BOB_MAX_CONCURRENT_FEATURES`` (default 3) concurrent feature workers,
eliminating the single-feature-blocks-round failure mode.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def __getattr__(name: str) -> Any:
    """Lazy re-exports from bob.orchestrator.run_loop to break circular import.

    orchestrator/__init__.py imports ConcurrentDispatchSlot from this module,
    and this module would normally import from bob.orchestrator.run_loop —
    which triggers orchestrator/__init__.py again (circular).  Deferring the
    run_loop imports to attribute access time breaks the cycle.
    """
    if name in ("dispatch_concurrent_features", "current_concurrency_slots", "_resolve_max_concurrent_features"):
        from bob.orchestrator.run_loop import (  # noqa: F401
            dispatch_concurrent_features as _dcf,
            current_concurrency_slots as _ccs,
            _resolve_max_concurrent_features as _rmcf,
        )
        _mapping = {
            "dispatch_concurrent_features": _dcf,
            "current_concurrency_slots": _ccs,
            "_resolve_max_concurrent_features": _rmcf,
        }
        return _mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ConcurrentDispatchSlot",
    "dispatch_concurrent_features",
    "current_concurrency_slots",
]


class ConcurrentDispatchSlot:
    """Represents a single in-flight concurrent feature dispatch.

    A :class:`ConcurrentDispatchSlot` wraps the asyncio task and metadata
    for one feature being executed concurrently.  The orchestrator maintains
    a pool of these slots (up to ``BOB_MAX_CONCURRENT_FEATURES``) and
    replaces each slot when its task completes.

    Args:
        feature: The feature object being dispatched.
        task: The :class:`asyncio.Task` executing the feature worker.

    Attributes:
        feature: The feature being dispatched.
        feature_id: The feature's ``.id`` attribute (convenience accessor).
        task: The asyncio task running the worker.
        done: ``True`` once the task has completed (succeeded or failed).
        result: The task return value on success, or ``None`` on failure.
        error: The exception's string representation on failure, or ``None``.
    """

    def __init__(self, feature: Any, task: asyncio.Task) -> None:
        if feature is None:
            raise ValueError("feature must not be None")
        if not isinstance(task, asyncio.Task):
            raise ValueError(f"task must be an asyncio.Task, got {type(task).__name__!r}")
        self.feature = feature
        self.feature_id: str = getattr(feature, "id", repr(feature))
        self.task: asyncio.Task = task
        self.done: bool = False
        self.result: Any = None
        self.error: str | None = None

    def is_done(self) -> bool:
        """Return ``True`` if the underlying task has finished."""
        return self.task.done()

    def collect(self) -> dict[str, Any]:
        """Collect the task outcome once done.

        Marks the slot as ``done`` and populates ``.result`` / ``.error``.
        Safe to call multiple times; subsequent calls return the cached outcome.

        Returns:
            A result dict::

                {
                    "feature_id": str,
                    "success":    bool,
                    "result":     Any,
                    "error":      str | None,
                }

        Raises:
            RuntimeError: If the task has not yet completed.
        """
        if self.done:
            return {
                "feature_id": self.feature_id,
                "success": self.error is None,
                "result": self.result,
                "error": self.error,
            }
        if not self.task.done():
            raise RuntimeError(
                f"Cannot collect slot for {self.feature_id!r}: task is still running"
            )
        self.done = True
        exc = self.task.exception()
        if exc is not None:
            self.error = str(exc)
            logger.warning(
                "Dispatch slot for %s failed: %s", self.feature_id, self.error
            )
        else:
            self.result = self.task.result()
        return {
            "feature_id": self.feature_id,
            "success": self.error is None,
            "result": self.result,
            "error": self.error,
        }

    def __repr__(self) -> str:
        status = "done" if self.done else ("running" if not self.task.done() else "finished")
        return f"ConcurrentDispatchSlot(feature_id={self.feature_id!r}, status={status!r})"
