"""
Graceful shutdown handler for Bob3 (F117).

Catches SIGINT and SIGTERM to set a flag. The actual shutdown work
(database I/O, subprocess shutdown) is performed by the main loop at
safe points — NOT inside the signal handler. Per POSIX, signal handlers
should be async-signal-safe; doing arbitrary I/O can deadlock if the
signal interrupts code that holds a non-reentrant lock (the most common
case: SIGINT firing during ``conn.commit()`` deadlocks against the
SQLite connection lock when the handler tries to commit again).

The handler's responsibilities are split:

* :meth:`GracefulShutdownHandler._handle_signal` — runs in signal
  context. Only sets ``shutdown_requested = True`` and logs a brief
  message. On a second signal, raises :class:`SystemExit` (allowed in
  handler context). Does NOT touch the database, subprocesses, or any
  other non-reentrant resources.

* :meth:`GracefulShutdownHandler._perform_shutdown` — runs in normal
  code context (called by the main loop). Performs all the actual
  shutdown actions: checkpoint, mark feature interrupted, stop MCP
  server.

Usage::

    from bob3.signal_handler import GracefulShutdownHandler

    handler = GracefulShutdownHandler(conn=conn, project_id=project_id)
    handler.install()

    # ... run sub-agent ...
    # handler.set_active_feature(feature_id, feature_data)
    # In the main loop, between safe points:
    #     if handler.shutdown_requested:
    #         handler._perform_shutdown()
    #         break

    handler.uninstall()
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone
from types import FrameType
from typing import Any

logger = logging.getLogger(__name__)

# Timeout for waiting for sub-agent to reach safe point
_SAFE_POINT_TIMEOUT_SECONDS = 30


class GracefulShutdownHandler:
    """Manages graceful shutdown on SIGINT/SIGTERM for Bob3.

    Installs signal handlers that set a flag and perform shutdown actions
    including checkpointing the current feature state, updating the
    feature status to 'interrupted', and stopping the MCP server.

    Attributes:
        shutdown_requested: True once a signal has been received.
        shutdown_complete: True once all shutdown actions have finished.
    """

    def __init__(
        self,
        conn: Any,
        project_id: str,
    ) -> None:
        self._conn = conn
        self._project_id = project_id

        self.shutdown_requested: bool = False
        self.shutdown_complete: bool = False

        self._active_feature_id: str | None = None
        self._active_feature_data: dict | None = None
        self._active_run_id: str | None = None
        self._execution_start_ms: int | None = None
        self._cost_so_far: float | None = None

        self._original_sigint: signal.Handlers | None = None
        self._original_sigterm: signal.Handlers | None = None
        self._installed: bool = False
        self._lock = threading.Lock()

    def set_active_feature(
        self,
        feature_id: str,
        feature_data: dict,
        *,
        run_id: str | None = None,
        execution_start_ms: int | None = None,
        cost_so_far: float | None = None,
    ) -> None:
        """Register the currently executing feature for checkpoint on interrupt.

        Args:
            feature_id: The feature ID being executed.
            feature_data: Dict with feature information (id, name, description, etc.).
            run_id: Optional sub_agent_runs ID for the current execution.
            execution_start_ms: Optional epoch milliseconds when execution started.
            cost_so_far: Optional accumulated cost at this point.
        """
        with self._lock:
            self._active_feature_id = feature_id
            self._active_feature_data = feature_data
            self._active_run_id = run_id
            self._execution_start_ms = execution_start_ms
            self._cost_so_far = cost_so_far

    def clear_active_feature(self) -> None:
        """Clear the active feature (e.g. after successful completion)."""
        with self._lock:
            self._active_feature_id = None
            self._active_feature_data = None
            self._active_run_id = None
            self._execution_start_ms = None
            self._cost_so_far = None

    def install(self) -> None:
        """Install SIGINT and SIGTERM handlers.

        Saves the original handlers so they can be restored later.
        """
        if self._installed:
            return

        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._installed = True
        logger.debug("Graceful shutdown handlers installed (SIGINT, SIGTERM)")

    def uninstall(self) -> None:
        """Restore the original signal handlers."""
        if not self._installed:
            return

        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

        self._installed = False
        logger.debug("Graceful shutdown handlers uninstalled")

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        """Signal handler callback for SIGINT/SIGTERM.

        This runs in signal context. It MUST be async-signal-safe, so it
        only sets the ``shutdown_requested`` flag and logs a brief
        message. The main loop is responsible for noticing the flag at a
        safe point and calling :meth:`_perform_shutdown` from regular
        (non-handler) code.

        Doing database I/O, subprocess control, or anything else that
        may take a non-reentrant lock here can deadlock the process if
        the signal interrupted code that already holds that lock (e.g.,
        ``conn.commit()`` on the main thread).

        On a second signal, raises :class:`SystemExit` to force
        immediate exit. Raising ``SystemExit`` from a handler is
        permitted (the interpreter handles it as a regular exception).
        """
        sig_name = signal.Signals(signum).name

        if self.shutdown_requested:
            # Second signal: user wants out NOW. SystemExit unwinds the
            # main thread; this is safe to raise from a handler.
            logger.warning(
                "Received %s again during shutdown — forcing immediate exit",
                sig_name,
            )
            raise SystemExit(128 + signum)

        # First signal: set the flag and return. The main loop polls
        # ``shutdown_requested`` at safe points and will call
        # ``_perform_shutdown`` from there. Do NOT perform shutdown
        # work here — see module docstring for why.
        logger.warning(
            "Received %s — graceful shutdown requested; finishing current step",
            sig_name,
        )
        self.shutdown_requested = True

    def _perform_shutdown(self) -> None:
        """Execute the graceful shutdown sequence.

        This MUST be called from regular code paths only, NOT from a
        signal handler. It performs database I/O (checkpoint creation,
        feature status update, ``conn.commit()``) and subprocess I/O
        (stopping the MCP server) — all of which can deadlock if invoked
        while the interrupted code holds a non-reentrant lock.

        The intended caller is the main orchestration loop, which polls
        :attr:`shutdown_requested` between feature executions and calls
        this method from the resulting normal control flow.

        Steps:

        1. Create checkpoint with current state
        2. Mark feature as 'interrupted'
        3. Stop MCP server
        4. Log resume message

        Idempotent: calling this more than once is harmless (it sets
        ``shutdown_complete = True`` and subsequent calls re-run the
        sequence; in practice the main loop calls it exactly once).
        """
        from bob3.db import create_checkpoint, update_feature
        from bob3.mcp_lifecycle import stop_mcp_server

        logger.info("Graceful shutdown: starting checkpoint sequence")

        feature_id = self._active_feature_id
        feature_data = self._active_feature_data

        if feature_id and feature_data:
            # Step 1: Create checkpoint
            try:
                state = {
                    "feature_id": feature_id,
                    "feature_name": feature_data.get("name", ""),
                    "feature_status_before": feature_data.get("status", "executing"),
                    "project_id": self._project_id,
                    "run_id": self._active_run_id,
                    "interrupted_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "graceful_shutdown",
                }
                state_snapshot = json.dumps(state)

                duration_ms = None
                if self._execution_start_ms is not None:
                    duration_ms = int(time.time() * 1000) - self._execution_start_ms

                checkpoint = create_checkpoint(
                    project_id=self._project_id,
                    feature_id=feature_id,
                    checkpoint_type="manual",
                    state_snapshot=state_snapshot,
                    cost_at_checkpoint=self._cost_so_far,
                    duration_at_checkpoint_ms=duration_ms,
                )
                logger.info(
                    "Checkpoint created: %s for feature '%s'",
                    checkpoint.id,
                    feature_id,
                )
            except Exception as exc:
                logger.error(
                    "Failed to create checkpoint for feature '%s': %s",
                    feature_id,
                    exc,
                )

            # Step 2: Mark feature as interrupted
            try:
                update_feature(feature_id, status="interrupted")
                logger.info("Feature '%s' marked as 'interrupted'", feature_id)
            except Exception as exc:
                logger.error(
                    "Failed to mark feature '%s' as interrupted: %s",
                    feature_id,
                    exc,
                )

            # Commit any outstanding state on the caller's connection.
            # ``db.create_checkpoint`` and ``db.update_feature`` open
            # their own connections and commit there, but if the caller
            # holds an additional connection (e.g. for read-only views)
            # we still flush it here so the resume path sees a
            # consistent snapshot.
            if self._conn is not None:
                try:
                    self._conn.commit()
                except Exception as exc:
                    logger.error("Failed to commit shutdown state: %s", exc)
        else:
            logger.info(
                "Graceful shutdown: no active feature to checkpoint"
            )

        # Step 3: Stop MCP server
        try:
            stop_mcp_server()
            logger.info("MCP server stopped")
        except Exception as exc:
            logger.error("Failed to stop MCP server: %s", exc)

        # Step 4: Log resume message
        logger.info("Interrupted. Run `bob3 run` to resume.")
        print("\nInterrupted. Run `bob3 run` to resume.")

        self.shutdown_complete = True
