"""Per-feature subagent watchdog (1d13b1f6).

Arms an asyncio task that runs on the orchestrator's event loop — NOT inside
the subagent coroutine — and forcibly cancels a hung subagent at a hard
wall-clock deadline derived from BOB3_FEATURE_TIMEOUT_SECONDS.

The problem this solves:

    The 3600s _DEFAULT_FEATURE_TIMEOUT_SECONDS in run_loop.py is wrapped in
    asyncio.wait_for(...) around spawn_sub_agent(...).  If asyncio scheduling
    delays that cancellation (e.g. the event loop is itself wedged inside the
    coroutine awaiting a blocking tool call), the run-loop stays blocked.

    An external asyncio.create_task() watchdog — created before the await —
    holds the subagent PID and fires os.kill(SIGTERM/SIGKILL) plus
    cancels the parent dispatch Task at the hard deadline.  Because it runs
    on the event loop independently of the awaited coroutine, it fires even
    when the awaiting coroutine is stuck.

Public API
----------
compute_deadline(timeout_seconds)
    Return an absolute monotonic deadline (float) from now + timeout_seconds.

cancel_subagent_at_deadline(pid, task, deadline, feature_id)
    Async coroutine: sleeps until deadline, then signals the PID and cancels
    the task.  No-op when the process has already exited.

arm_feature_watchdog(pid, task, feature_id, timeout_seconds)
    Wraps cancel_subagent_at_deadline in asyncio.create_task() and returns the
    watchdog Task.  The caller should await or cancel the watchdog once the
    subagent finishes normally.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

logger = logging.getLogger(__name__)

_DEFAULT_FEATURE_TIMEOUT_SECONDS = 3600  # match run_loop.py constant


def compute_deadline(timeout_seconds: float) -> float:
    """Return the absolute monotonic deadline for a subagent dispatch.

    Args:
        timeout_seconds: Maximum allowed wall-clock seconds from now.

    Returns:
        Absolute monotonic time (time.monotonic() + timeout_seconds).

    Raises:
        ValueError: When timeout_seconds is non-positive.
    """
    if timeout_seconds <= 0:
        raise ValueError(
            f"timeout_seconds must be positive; got {timeout_seconds!r}"
        )
    return time.monotonic() + timeout_seconds


def _pid_is_alive(pid: int) -> bool:
    """Return True if ``pid`` is alive (signal-0 probe)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it — treat as alive.
        return True


async def cancel_subagent_at_deadline(
    pid: int,
    task: asyncio.Task,  # type: ignore[type-arg]
    deadline: float,
    feature_id: str,
) -> None:
    """Async watchdog coroutine: cancel the subagent at a hard wall-clock deadline.

    Designed to be scheduled via asyncio.create_task() BEFORE the caller awaits
    spawn_sub_agent(), so it runs independently on the event loop and fires
    regardless of whether the awaited coroutine is progressing.

    Algorithm:
        1. Sleep until ``deadline`` (time.monotonic()-based; fine-grained).
        2. If the subagent process already exited — return immediately (no-op).
        3. Send SIGTERM to ``pid``; wait up to 5 seconds for clean exit.
        4. If still alive, send SIGKILL.
        5. Cancel the caller's asyncio Task so the event-loop await unblocks.

    Safety:
        - Never signals PID ≤ 1 or os.getpid() (itself).
        - Catches asyncio.CancelledError so the watchdog can be cancelled
          cleanly when the subagent finishes on its own.

    Args:
        pid: OS process ID of the spawned subagent (claude Node.js process).
        task: The asyncio.Task awaiting spawn_sub_agent(); will be cancelled
              after the PID is signalled.
        deadline: Absolute monotonic time after which cancellation fires.
        feature_id: Feature UUID — used only for log messages.
    """
    own_pid = os.getpid()
    try:
        # Sleep until the deadline fires.  Use a tight loop so we honour
        # cancellation (i.e. watchdog.cancel()) promptly when the subagent
        # finishes normally and the caller cancels the watchdog task.
        remaining = deadline - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Check whether the process already exited while we were sleeping.
        if pid <= 1 or pid == own_pid:
            logger.debug(
                "Watchdog for feature %s: PID %d is unsafe to signal; aborting",
                feature_id[:8],
                pid,
            )
            return

        if not _pid_is_alive(pid):
            logger.debug(
                "Watchdog for feature %s: PID %d already exited before deadline; no-op",
                feature_id[:8],
                pid,
            )
            return

        # Deadline reached and process is still alive — start eviction.
        logger.warning(
            "Watchdog for feature %s: deadline reached with PID %d still alive; "
            "sending SIGTERM",
            feature_id[:8],
            pid,
        )

        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

        # Wait up to 5 seconds for clean exit after SIGTERM.
        grace_end = time.monotonic() + 5.0
        while time.monotonic() < grace_end:
            if not _pid_is_alive(pid):
                break
            await asyncio.sleep(0.25)

        if _pid_is_alive(pid):
            logger.warning(
                "Watchdog for feature %s: PID %d did not exit after SIGTERM grace; "
                "sending SIGKILL",
                feature_id[:8],
                pid,
            )
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        # Cancel the dispatcher task so the orchestrator run-loop unblocks.
        if not task.done():
            logger.warning(
                "Watchdog for feature %s: cancelling dispatch task after PID %d signalled",
                feature_id[:8],
                pid,
            )
            task.cancel()

    except asyncio.CancelledError:
        # The caller cancelled the watchdog (normal path when subagent finished).
        logger.debug(
            "Watchdog for feature %s: cancelled cleanly (subagent finished normally)",
            feature_id[:8],
        )
        raise


def arm_feature_watchdog(
    pid: int,
    task: asyncio.Task,  # type: ignore[type-arg]
    feature_id: str,
    timeout_seconds: float | None = None,
) -> asyncio.Task:  # type: ignore[type-arg]
    """Spawn an external timer that cancels the subagent at a hard deadline.

    Creates an asyncio.create_task() watchdog that fires independently of the
    awaited coroutine.  The caller MUST cancel the returned watchdog task once
    the subagent completes normally:

        watchdog = arm_feature_watchdog(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Args:
        pid: OS PID of the spawned subagent.
        task: The asyncio.Task whose coroutine awaits spawn_sub_agent().
        feature_id: Feature UUID (for log messages).
        timeout_seconds: Hard deadline in seconds.  When None, reads
            BOB3_FEATURE_TIMEOUT_SECONDS from the environment, defaulting to
            _DEFAULT_FEATURE_TIMEOUT_SECONDS (3600).

    Returns:
        The watchdog asyncio.Task.
    """
    if timeout_seconds is None:
        timeout_seconds = _resolve_timeout_seconds()

    deadline = compute_deadline(timeout_seconds)

    watchdog_task = asyncio.create_task(
        cancel_subagent_at_deadline(pid, task, deadline, feature_id),
        name=f"feature-watchdog-{feature_id[:8]}",
    )
    logger.debug(
        "Armed watchdog for feature %s: PID=%d deadline=+%.0fs",
        feature_id[:8],
        pid,
        timeout_seconds,
    )
    return watchdog_task


def _resolve_timeout_seconds() -> float:
    """Read BOB3_FEATURE_TIMEOUT_SECONDS from the environment.

    Returns the configured timeout, falling back to
    _DEFAULT_FEATURE_TIMEOUT_SECONDS on parse errors or non-positive values.
    """
    import os as _os
    raw = _os.environ.get("BOB3_FEATURE_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    if value <= 0:
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    return value


def create_feature_watchdog(
    pid: int,
    task: asyncio.Task,  # type: ignore[type-arg]
    feature_id: str,
    timeout_seconds: float | None = None,
) -> asyncio.Task:  # type: ignore[type-arg]
    """Create and arm a per-feature asyncio watchdog task.

    Canonical entry point for the per-feature subagent watchdog feature
    (7d197945).  Spawns an ``asyncio.create_task()`` watchdog that runs on the
    orchestrator event loop independently of the awaited subagent coroutine.
    Fires SIGTERM + SIGKILL at a hard wall-clock deadline and cancels the
    dispatcher Task so the run-loop ``await`` unblocks.

    The caller MUST cancel the returned task once the subagent finishes::

        watchdog = create_feature_watchdog(pid, current_task, feature_id)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Args:
        pid: OS PID of the spawned subagent.
        task: The asyncio.Task whose coroutine awaits spawn_sub_agent().
        feature_id: Feature UUID (for log messages).
        timeout_seconds: Hard deadline in seconds.  When None, reads
            BOB3_FEATURE_TIMEOUT_SECONDS from the environment, defaulting to
            _DEFAULT_FEATURE_TIMEOUT_SECONDS (3600).

    Returns:
        The watchdog asyncio.Task.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def cancel_subagent_forcibly(pid: int, feature_id: str = "") -> None:
    """Forcibly cancel a subagent by sending SIGTERM then SIGKILL.

    Synchronous helper for cancelling a subagent OS process.  Sends SIGTERM,
    waits up to 5 seconds for a clean exit, then sends SIGKILL if still alive.
    Safe to call when the process has already exited (no-op in that case).

    Args:
        pid: OS process ID of the subagent to cancel.  Must be positive and
            not equal to the current process PID.
        feature_id: Optional feature UUID for log messages.

    Raises:
        ValueError: When ``pid`` is non-positive or equals the current process.
    """
    import time as _time

    if pid <= 0:
        raise ValueError(f"pid must be positive; got {pid!r}")
    own_pid = os.getpid()
    if pid == own_pid:
        raise ValueError(
            f"pid {pid!r} is the current process; refusing to self-signal"
        )

    if not _pid_is_alive(pid):
        logger.debug(
            "cancel_subagent_forcibly: PID %d already exited (feature %s)",
            pid,
            feature_id[:8] if feature_id else "",
        )
        return

    logger.warning(
        "cancel_subagent_forcibly: sending SIGTERM to PID %d (feature %s)",
        pid,
        feature_id[:8] if feature_id else "",
    )
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    grace_end = _time.monotonic() + 5.0
    while _time.monotonic() < grace_end:
        if not _pid_is_alive(pid):
            return
        _time.sleep(0.1)

    if _pid_is_alive(pid):
        logger.warning(
            "cancel_subagent_forcibly: PID %d still alive after grace; sending SIGKILL",
            pid,
            feature_id[:8] if feature_id else "",
        )
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
