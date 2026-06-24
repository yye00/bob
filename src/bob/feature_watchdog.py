"""Public API for the per-feature subagent watchdog (bb5d6c27).

Arms an asyncio task that runs on the orchestrator's event loop — NOT inside
the subagent coroutine — and forcibly cancels a hung subagent at a hard
wall-clock deadline derived from BOB_FEATURE_TIMEOUT_SECONDS.

The problem this solves
-----------------------
The run_loop's ``asyncio.wait_for(spawn_sub_agent(...), timeout=T)`` fires only
if the event loop can schedule the cancellation callback.  When the awaited
coroutine is blocked inside a synchronous tool call (e.g. an unscoped pytest
run), the event-loop may not schedule the timeout handler until the blocking
call returns — which is never.

An external ``asyncio.create_task()`` watchdog created BEFORE the await holds
the subagent OS PID and sends SIGTERM / SIGKILL independently of the awaited
coroutine.  It also cancels the dispatcher Task so the ``await`` finally
unblocks.

Public names
------------
FeatureWatchdog
    Context-manager wrapper that arms a watchdog for the duration of a block.
spawn_feature_watchdog
    Low-level helper: arms a watchdog and returns the asyncio.Task.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Any

import os
import signal

from bob.orchestrator.feature_watchdog import (
    _pid_is_alive,
    arm_feature_watchdog,
    cancel_subagent_at_deadline,
    compute_deadline,
)

__all__ = [
    "FeatureWatchdog",
    "FeatureSubagentWatchdog",
    "spawn_feature_watchdog",
    "spawn_feature_timeout_watchdog",
    "spawn_subagent_watchdog",
    "start_feature_watchdog",
    "create_subagent_watchdog",
    "cancel_subagent_at_deadline",
    "cancel_subagent_by_pid",
    "compute_deadline",
]

logger = logging.getLogger(__name__)


class FeatureWatchdog:
    """Context-manager that arms a per-feature asyncio watchdog.

    Usage::

        task = asyncio.current_task()
        async with FeatureWatchdog(pid=subagent_pid, task=task,
                                   feature_id=fid, timeout_seconds=3600):
            result = await spawn_sub_agent(...)

    When the context exits normally the watchdog is cancelled.
    When the deadline fires first, the watchdog signals the PID and
    cancels the dispatcher task so the ``await`` unblocks.

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent (claude Node.js process).
    task:
        The asyncio.Task whose coroutine is awaiting the subagent.
    feature_id:
        Feature UUID — used for log messages.
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.
    """

    def __init__(
        self,
        pid: int,
        task: "asyncio.Task[Any]",
        feature_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        self._pid = pid
        self._task = task
        self._feature_id = feature_id
        self._timeout_seconds = timeout_seconds
        self._watchdog_task: "asyncio.Task[None] | None" = None

    async def __aenter__(self) -> "FeatureWatchdog":
        self._watchdog_task = arm_feature_watchdog(
            pid=self._pid,
            task=self._task,
            feature_id=self._feature_id,
            timeout_seconds=self._timeout_seconds,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
        return None

    @property
    def watchdog_task(self) -> "asyncio.Task[None] | None":
        """The underlying asyncio watchdog task, or None before context entry."""
        return self._watchdog_task


def spawn_feature_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn an external timer watchdog that cancels the subagent at a hard deadline.

    Wraps ``bob.orchestrator.feature_watchdog.arm_feature_watchdog``.  The
    caller MUST cancel the returned task once the subagent completes normally::

        watchdog = spawn_feature_watchdog(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent.
    task:
        The asyncio.Task whose coroutine awaits the subagent.
    feature_id:
        Feature UUID (for log messages).
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def start_feature_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Start a per-feature subagent watchdog that cancels a hung subagent at a hard deadline.

    This is the canonical entry point for the per-feature subagent watchdog feature
    (c238c4a2).  Creates an ``asyncio.create_task()`` watchdog on the orchestrator
    event loop that fires independently of the awaited subagent coroutine, solving
    the stall described in the feature description: even when
    ``asyncio.wait_for(spawn_sub_agent(...), timeout=T)`` cannot schedule its
    cancellation callback (e.g. the coroutine is blocked inside an unscoped pytest
    run), this external watchdog fires at the hard wall-clock deadline.

    The caller MUST cancel the returned task once the subagent finishes normally::

        watchdog = start_feature_watchdog(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent (claude Node.js process).
    task:
        The asyncio.Task whose coroutine awaits the subagent.
    feature_id:
        Feature UUID (for log messages).
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def create_subagent_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Create and arm a per-feature subagent watchdog task.

    Canonical entry point used by the run_loop integration path.  Spawns an
    ``asyncio.create_task()`` watchdog that runs on the orchestrator event loop,
    independent of the awaited subagent coroutine, and forcibly cancels the
    hung subagent at a hard wall-clock deadline.

    The caller MUST cancel the returned task once the subagent finishes::

        watchdog = create_subagent_watchdog(pid, current_task, feature_id)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent (claude Node.js process).
    task:
        The asyncio.Task whose coroutine awaits the subagent.
    feature_id:
        Feature UUID (for log messages).
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def spawn_subagent_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn an external timer watchdog that cancels a hung subagent at a hard deadline.

    This is the canonical entry point for the run_loop integration path.  Creates
    an ``asyncio.create_task()`` watchdog running on the orchestrator event loop,
    independent of the awaited subagent coroutine, so it fires regardless of
    whether the coroutine is blocked inside a synchronous tool call (e.g. a
    50-minute unscoped pytest run).

    The watchdog holds the subagent OS PID and at the deadline:
    1. Sends SIGTERM to the PID and waits 5 s for a clean exit.
    2. If still alive, sends SIGKILL.
    3. Cancels the caller's asyncio.Task so the ``await`` unblocks.

    The caller MUST cancel the returned task once the subagent completes normally::

        watchdog = spawn_subagent_watchdog(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent (claude Node.js process).
    task:
        The asyncio.Task whose coroutine awaits the subagent.
    feature_id:
        Feature UUID (for log messages).
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def cancel_subagent_by_pid(pid: int, feature_id: str = "") -> None:
    """Synchronously cancel a subagent process by OS PID.

    Sends SIGTERM to the process, waits up to 5 seconds for clean exit,
    then sends SIGKILL if still alive.  Safe to call when the process has
    already exited (no-op in that case).

    Args:
        pid: OS process ID of the subagent to cancel.
        feature_id: Optional feature UUID for log messages.

    Raises:
        ValueError: If ``pid`` is non-positive or equals the current process PID.
    """
    import time as _time

    if pid <= 0:
        raise ValueError(f"pid must be positive; got {pid!r}")
    own_pid = os.getpid()
    if pid == own_pid:
        raise ValueError(f"pid {pid!r} is the current process; refusing to self-signal")

    if not _pid_is_alive(pid):
        logger.debug(
            "cancel_subagent_by_pid: PID %d already exited (feature %s)",
            pid,
            feature_id[:8] if feature_id else "",
        )
        return

    logger.warning(
        "cancel_subagent_by_pid: sending SIGTERM to PID %d (feature %s)",
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
            "cancel_subagent_by_pid: PID %d still alive after SIGTERM grace; sending SIGKILL",
            pid,
        )
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


class FeatureSubagentWatchdog(FeatureWatchdog):
    """Context-manager watchdog for per-feature subagent cancellation (789440d8).

    Identical to ``FeatureWatchdog`` but exported under the AC-required name
    ``FeatureSubagentWatchdog``.  Spawns an ``asyncio.create_task()`` watchdog
    on the orchestrator event loop that fires at a hard wall-clock deadline
    independently of the awaited subagent coroutine.

    Usage::

        task = asyncio.current_task()
        async with FeatureSubagentWatchdog(pid=subagent_pid, task=task,
                                           feature_id=fid, timeout_seconds=3600):
            result = await spawn_sub_agent(...)

    See ``FeatureWatchdog`` for full parameter documentation.
    """


def spawn_feature_timeout_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn a per-feature asyncio watchdog that cancels a hung subagent at a hard deadline.

    This is the canonical entry point required by the per-feature subagent
    watchdog feature (2bd6f598).  Creates an ``asyncio.create_task()`` watchdog
    that runs on the orchestrator event loop independently of the awaited
    subagent coroutine, and forcibly cancels the process at a hard wall-clock
    deadline derived from ``BOB_FEATURE_TIMEOUT_SECONDS``.

    Unlike the timeout inside the awaited coroutine (``asyncio.wait_for``),
    this watchdog fires even when the coroutine is blocked inside a synchronous
    tool call (e.g. a 50-minute unscoped pytest run) because it runs as a
    separate ``asyncio.Task`` on the same event loop.

    The caller MUST cancel the returned task once the subagent completes::

        watchdog = spawn_feature_timeout_watchdog(pid, current_task, feature_id)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

    Parameters
    ----------
    pid:
        OS PID of the spawned subagent (claude Node.js process).
    task:
        The asyncio.Task whose coroutine awaits the subagent.
    feature_id:
        Feature UUID (for log messages).
    timeout_seconds:
        Hard deadline in seconds.  ``None`` reads from
        ``BOB_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )
