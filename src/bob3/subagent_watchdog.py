"""Per-feature subagent watchdog — external timer cancels hung subagent (9089a21d).

Public API required by feature 9089a21d-be23-4d92-ba13-f1825f388af7:

SubagentWatchdog
    Async context-manager that arms a watchdog for the duration of a subagent
    dispatch block.  Cancels the watched task and signals the subagent PID if
    the hard deadline fires before the block exits.

spawn_watchdog_task
    Low-level function: creates an asyncio.create_task() watchdog and returns
    the task.  The caller must cancel the returned task when the subagent
    finishes normally.

Both entry points delegate to bob3.orchestrator.feature_watchdog, which
implements the actual SIGTERM/SIGKILL/task-cancel logic.

Problem solved
--------------
The run_loop's asyncio.wait_for(spawn_sub_agent(...), timeout=T) fires only
when the event loop can schedule the cancellation callback.  If the awaited
coroutine is blocked inside a synchronous tool call (e.g. an unscoped pytest
run lasting 50+ minutes), the event loop cannot schedule the timeout handler
until the blocking call returns.

An asyncio.create_task() watchdog created BEFORE the await runs on the event
loop independently and fires regardless of whether the coroutine is progressing.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Any

from bob3.orchestrator.feature_watchdog import arm_feature_watchdog
from bob3.feature_watchdog import cancel_subagent_by_pid

__all__ = [
    "SubagentWatchdog",
    "spawn_watchdog",
    "spawn_watchdog_task",
    "spawn_feature_watchdog",
    "create_watchdog_task",
    "cancel_subagent_task",
    "cancel_subagent",
    "cancel_subagent_forcibly",
    "cancel_subagent_process",
    "cancel_subagent_on_timeout",
]

logger = logging.getLogger(__name__)


class SubagentWatchdog:
    """Async context-manager that arms a per-feature subagent watchdog.

    Spawns an ``asyncio.create_task()`` watchdog on the orchestrator event loop
    before the caller awaits a subagent dispatch.  The watchdog fires at a hard
    wall-clock deadline derived from ``BOB3_FEATURE_TIMEOUT_SECONDS``,
    independently of whether the awaited coroutine is progressing.

    At the deadline the watchdog:

    1. Sends SIGTERM to ``pid`` and waits up to 5 s for a clean exit.
    2. Sends SIGKILL if the process is still alive.
    3. Cancels the caller's asyncio.Task so the ``await`` finally unblocks.

    Usage::

        task = asyncio.current_task()
        async with SubagentWatchdog(pid=subagent_pid, task=task,
                                    feature_id=fid, timeout_seconds=3600):
            result = await spawn_sub_agent(...)

    When the context exits normally the watchdog is cancelled cleanly.

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
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.
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

    async def __aenter__(self) -> "SubagentWatchdog":
        self._watchdog_task = arm_feature_watchdog(
            pid=self._pid,
            task=self._task,
            feature_id=self._feature_id,
            timeout_seconds=self._timeout_seconds,
        )
        logger.debug(
            "SubagentWatchdog armed for feature %s PID=%d",
            self._feature_id[:8],
            self._pid,
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


def spawn_watchdog_task(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn an external watchdog task that cancels a hung subagent at a hard deadline.

    Creates an ``asyncio.create_task()`` watchdog that runs on the orchestrator
    event loop, independent of the awaited subagent coroutine, and fires regardless
    of whether the coroutine is blocked inside a synchronous tool call.

    The caller MUST cancel the returned task once the subagent completes normally::

        watchdog = spawn_watchdog_task(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

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
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.

    Raises
    ------
    ValueError
        When ``timeout_seconds`` is non-positive (delegated to
        ``compute_deadline``).
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def spawn_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn a per-feature subagent watchdog that cancels a hung subagent at a hard deadline.

    Canonical entry point required by feature fb969047.  Creates an
    ``asyncio.create_task()`` watchdog on the orchestrator event loop,
    independent of the awaited subagent coroutine, that fires at a hard
    wall-clock deadline derived from ``BOB3_FEATURE_TIMEOUT_SECONDS``.

    At the deadline the watchdog:
    1. Sends SIGTERM to ``pid`` and waits up to 5 s for a clean exit.
    2. Sends SIGKILL if the process is still alive.
    3. Cancels the caller's asyncio.Task so the ``await`` finally unblocks.

    The caller MUST cancel the returned task once the subagent completes normally::

        watchdog = spawn_watchdog(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

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
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.

    Raises
    ------
    ValueError
        When ``timeout_seconds`` is non-positive.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def create_watchdog_task(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Create and arm a per-feature subagent watchdog asyncio.Task.

    Canonical alias for ``spawn_watchdog_task``.  Spawns an
    ``asyncio.create_task()`` watchdog on the orchestrator event loop,
    independent of the awaited subagent coroutine, that fires at a hard
    wall-clock deadline and forcibly cancels the hung subagent.

    The caller MUST cancel the returned task once the subagent finishes::

        watchdog = create_watchdog_task(pid, current_task, feature_id, timeout)
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
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.

    Raises
    ------
    ValueError
        When ``timeout_seconds`` is non-positive.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def spawn_feature_watchdog(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn an external watchdog that cancels a hung subagent at a hard deadline.

    Canonical entry point for the per-feature subagent watchdog pattern
    (feature 16835257).  Creates an ``asyncio.create_task()`` watchdog that
    runs on the orchestrator event loop, independent of the awaited subagent
    coroutine, and fires regardless of whether the coroutine is blocked inside
    a synchronous tool call.

    The watchdog holds the subagent OS PID and at the deadline:
    1. Sends SIGTERM to the PID and waits 5 s for a clean exit.
    2. If still alive, sends SIGKILL.
    3. Cancels the caller's asyncio.Task so the ``await`` unblocks.

    The caller MUST cancel the returned task once the subagent completes
    normally::

        watchdog = spawn_feature_watchdog(pid, current_task, feature_id, timeout)
        try:
            result = await spawn_sub_agent(...)
        finally:
            watchdog.cancel()

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
        ``BOB3_FEATURE_TIMEOUT_SECONDS``, defaulting to 3600.

    Returns
    -------
    asyncio.Task
        The watchdog task.  Cancel it when the subagent finishes normally.

    Raises
    ------
    ValueError
        When ``timeout_seconds`` is non-positive.
    """
    return arm_feature_watchdog(
        pid=pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=timeout_seconds,
    )


def cancel_subagent(pid: int, feature_id: str = "") -> None:
    """Synchronously cancel a subagent process by OS PID.

    Sends SIGTERM to ``pid``, waits up to 5 seconds for a clean exit, then
    sends SIGKILL if the process is still alive.  Safe to call when the
    process has already exited (no-op in that case).

    Parameters
    ----------
    pid:
        OS process ID of the subagent to cancel.
    feature_id:
        Optional feature UUID for log messages.

    Raises
    ------
    ValueError
        When ``pid`` is non-positive or equals the current process PID.
    """
    cancel_subagent_by_pid(pid=pid, feature_id=feature_id)


def cancel_subagent_task(pid: int, feature_id: str = "") -> None:
    """Cancel a subagent process by OS PID (required by feature fb969047).

    Canonical entry point for cancelling a hung subagent by its OS PID.
    Sends SIGTERM to ``pid``, waits up to 5 seconds for a clean exit, then
    sends SIGKILL if the process is still alive.  Safe to call when the
    process has already exited (no-op in that case).

    Parameters
    ----------
    pid:
        OS process ID of the subagent to cancel.
    feature_id:
        Optional feature UUID for log messages.

    Raises
    ------
    ValueError
        When ``pid`` is non-positive or equals the current process PID.
    """
    cancel_subagent_by_pid(pid=pid, feature_id=feature_id)


def cancel_subagent_forcibly(pid: int, feature_id: str = "") -> None:
    """Forcibly cancel a subagent process by OS PID.

    Canonical alias for ``cancel_subagent``.  Sends SIGTERM to ``pid``,
    waits up to 5 seconds for a clean exit, then sends SIGKILL if the
    process is still alive.  Safe to call when the process has already
    exited (no-op in that case).

    Parameters
    ----------
    pid:
        OS process ID of the subagent to cancel.
    feature_id:
        Optional feature UUID for log messages.

    Raises
    ------
    ValueError
        When ``pid`` is non-positive or equals the current process PID.
    """
    cancel_subagent_by_pid(pid=pid, feature_id=feature_id)


def cancel_subagent_process(pid: int, feature_id: str = "") -> None:
    """Cancel a hung subagent process by OS PID (AC: bob3.subagent_watchdog.cancel_subagent_process).

    Sends SIGTERM to the process, waits up to 5 seconds for a clean exit,
    then sends SIGKILL if the process is still alive.  Safe to call when
    the process has already exited (no-op in that case).

    This is the canonical entry point required by feature 3e2a4bee for the
    per-feature subagent watchdog — external timer cancels hung subagent
    independent of run-loop await.

    Parameters
    ----------
    pid:
        OS process ID of the subagent to cancel.
    feature_id:
        Optional feature UUID for log messages.

    Raises
    ------
    ValueError
        When ``pid`` is non-positive or equals the current process PID.
    """
    cancel_subagent_by_pid(pid=pid, feature_id=feature_id)


def cancel_subagent_on_timeout(pid: int, feature_id: str = "") -> None:
    """Cancel a hung subagent process when the per-feature watchdog timeout fires.

    This is the canonical entry point for feature 3992eeed — per-feature
    subagent watchdog that cancels hung subagents independent of run-loop
    await.  Called by the watchdog task when the hard wall-clock deadline
    derived from ``BOB3_FEATURE_TIMEOUT_SECONDS`` expires.

    Sends SIGTERM to ``pid``, waits up to 5 seconds for a clean exit, then
    sends SIGKILL if the process is still alive.  Safe to call when the
    process has already exited (no-op in that case).

    Parameters
    ----------
    pid:
        OS process ID of the subagent to cancel.
    feature_id:
        Optional feature UUID for log messages.

    Raises
    ------
    ValueError
        When ``pid`` is non-positive or equals the current process PID.
    """
    cancel_subagent_by_pid(pid=pid, feature_id=feature_id)
