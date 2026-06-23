"""Periodic resume timer — schedules mid-run resume scans for interrupted features.

Provides a lightweight timer wrapper that fires ``periodic_resume_scan`` on a
configurable interval (default 60 s) so that features marked 'interrupted'
mid-run are re-queued without waiting for an orchestrator restart.

Combined with the stuck-executing reaper (F-R7-501) this closes the two paths
by which the orchestrator silently stalls on rows it should re-dispatch.

Public API
----------
PeriodicResumeTimer(project_id, interval_seconds)
    Timer object.  Call ``start()`` to begin scheduling and ``stop()`` to cancel.

start_periodic_resume_timer(project_id, interval_seconds)
    Convenience factory: create and start a timer, return the instance.
"""

from __future__ import annotations

import logging
import threading

from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 60


class PeriodicResumeTimer:
    """Fire ``periodic_resume_scan`` every *interval_seconds* seconds.

    Thread-safe; ``start`` / ``stop`` are idempotent.

    Args:
        project_id: UUID of the project to scan.
        interval_seconds: How often to run the scan (default 60 s).
    """

    def __init__(
        self,
        project_id: str,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError(
                f"project_id must be a non-empty string, got {project_id!r}"
            )
        if interval_seconds <= 0:
            raise ValueError(
                f"interval_seconds must be positive, got {interval_seconds!r}"
            )
        self._project_id = project_id
        self._interval = interval_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Schedule the first scan tick.  Idempotent — safe to call multiple times."""
        with self._lock:
            if self._running:
                return
            self._running = True
        self._schedule()

    def stop(self) -> None:
        """Cancel any pending tick.  Idempotent — safe to call when not started."""
        with self._lock:
            self._running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    @property
    def is_running(self) -> bool:
        """True if the timer has been started and not yet stopped."""
        with self._lock:
            return self._running

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _schedule(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._timer = threading.Timer(self._interval, self._tick)
            self._timer.daemon = True
            self._timer.start()

    def _tick(self) -> None:
        try:
            promoted = periodic_resume_scan(self._project_id)
            if promoted:
                logger.info(
                    "periodic_resume_timer: promoted %d interrupted feature(s): %s",
                    len(promoted),
                    promoted,
                )
        except Exception:
            logger.debug(
                "periodic_resume_timer: scan raised unexpectedly; skipping tick",
                exc_info=True,
            )
        finally:
            self._schedule()


def start_periodic_resume_timer(
    project_id: str,
    interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
) -> PeriodicResumeTimer:
    """Create and start a :class:`PeriodicResumeTimer`.

    Args:
        project_id: UUID of the project to scan.
        interval_seconds: How often to run the scan (default 60 s).

    Returns:
        The running timer instance.  Call ``.stop()`` to cancel.
    """
    timer = PeriodicResumeTimer(project_id, interval_seconds)
    timer.start()
    return timer
