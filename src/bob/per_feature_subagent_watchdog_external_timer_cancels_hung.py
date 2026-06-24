"""Per-feature subagent watchdog: external timer cancels hung subagent (2a5431ca).

Problem
-------
The run_loop's ``asyncio.wait_for(spawn_sub_agent(...), timeout=T)`` relies on
the event loop to schedule the cancellation callback.  When the awaited
coroutine is blocked inside a synchronous tool call (e.g. an unscoped pytest
run lasting 50+ minutes), the event loop cannot schedule the timeout handler
until the blocking call returns — which may be never.

Solution
--------
``per_feature_subagent_watchdog_external_timer_cancels_hung`` spawns an
``asyncio.create_task()`` watchdog *before* the caller awaits
``spawn_sub_agent()``.  The watchdog runs on the orchestrator event loop,
independently of the awaited coroutine, and forcibly cancels the hung subagent
at a hard wall-clock deadline derived from ``BOB_FEATURE_TIMEOUT_SECONDS``.

At the deadline the watchdog:
1. Sends SIGTERM to the subagent PID and waits up to 5 s for a clean exit.
2. Sends SIGKILL if the process is still alive.
3. Cancels the caller's asyncio.Task so the ``await`` finally unblocks.

Usage
-----
::

    task = asyncio.current_task()
    watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
        pid=subagent_pid,
        task=task,
        feature_id=feature_id,
        timeout_seconds=3600,
    )
    try:
        result = await spawn_sub_agent(...)
    finally:
        watchdog.cancel()
"""

from __future__ import annotations

import asyncio
from typing import Any

from bob.orchestrator.feature_watchdog import arm_feature_watchdog

__all__ = ["per_feature_subagent_watchdog_external_timer_cancels_hung"]


def per_feature_subagent_watchdog_external_timer_cancels_hung(
    pid: int,
    task: "asyncio.Task[Any]",
    feature_id: str,
    timeout_seconds: float | None = None,
) -> "asyncio.Task[None]":
    """Spawn an external watchdog that cancels a hung subagent at a hard deadline.

    This function is the canonical entry point for the per-feature subagent
    watchdog pattern described in feature 2a5431ca.  It creates an
    ``asyncio.create_task()`` watchdog that runs on the orchestrator event loop,
    independent of the awaited subagent coroutine, and fires regardless of
    whether the coroutine is blocked inside a synchronous tool call.

    The caller MUST cancel the returned task once the subagent completes
    normally::

        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid, current_task, feature_id, timeout
        )
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
