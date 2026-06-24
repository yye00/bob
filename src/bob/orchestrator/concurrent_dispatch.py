"""Concurrent dispatch module for the Bob orchestrator.

Feature: Orchestrator dispatch concurrency — let multiple ready features run
in parallel instead of strict single-flight (71789dc8-6774-4129-8479-821d4781f0d7).

Introduces BOB_MAX_CONCURRENT_FEATURES (default 3) and two public functions:

:func:`dispatch_concurrent_features`
    Fill open concurrency slots with ready features and dispatch them as
    concurrent asyncio tasks.  Replaces the previous sequential
    ``result = await execute_feature(feature)`` call in the tick loop.

:func:`gather_and_reap`
    Collect outcomes from a list of asyncio tasks once they have completed,
    cancelling (reaping) any tasks that exceed their per-task deadline.
    Failure isolation ensures one bad task does not cancel peers.

The orchestrator tick loop becomes:

    tasks = asyncio.create_task(...)  # one per claimed feature
    results = await gather_and_reap(tasks, timeout=3600.0)
    # → reap stuck, return outcomes

This eliminates the single-feature-blocks-round failure mode: a hung
subagent is reaped independently of its peers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def dispatch_concurrent_features(
    loop: Any,
    *,
    worker: Any,
    active_feature_ids: "set[str] | None" = None,
    on_failure: Any = None,
) -> "list[dict[str, object]]":
    """Dispatch up to ``BOB_MAX_CONCURRENT_FEATURES`` ready features concurrently.

    Fills open concurrency slots with ready features from *loop*'s project and
    dispatches them as concurrent asyncio tasks, replacing the previous
    sequential ``result = await execute_feature(feature)`` call.

    Args:
        loop: The :class:`~bob.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the concurrency cap
            (``loop.max_concurrent_features``).
        worker: Async callable ``async def worker(feature) -> result`` invoked
            for each claimed feature.  Failures are isolated per feature.
        active_feature_ids: Optional set of feature IDs already in flight.
            Claimed features are added before dispatch so repeated calls within
            the same tick don't double-dispatch the same feature.
        on_failure: Optional callback ``on_failure(feature, exc)`` invoked
            after each worker failure.  Exceptions from the callback are
            swallowed so they cannot break the dispatch loop.

    Returns:
        List of result dicts — one per dispatched feature::

            {
                "feature_id": str,
                "success":    bool,
                "result":     Any,
                "error":      str | None,
            }

        Empty when no slots are open or no ready features are available.

    Raises:
        ValueError: If *loop* is ``None`` or *worker* is not callable.
    """
    from bob.orchestrator.run_loop import (
        dispatch_concurrent_features as _dispatch,
    )
    return await _dispatch(
        loop,
        worker=worker,
        active_feature_ids=active_feature_ids,
        on_failure=on_failure,
    )


async def gather_and_reap(
    tasks: "list[asyncio.Task[object]]",
    *,
    timeout: float | None = None,
) -> "list[dict[str, object]]":
    """Gather completed tasks and reap any that exceed the per-task deadline.

    Awaits all *tasks* concurrently.  When *timeout* is set, each task that
    has not completed within *timeout* seconds is cancelled (reaped) and its
    outcome is recorded as a failure with ``error="timeout"``.  Tasks that
    complete normally (success or exception) are recorded without
    cancellation.

    This combines the gather step (collect outcomes) with the reap step
    (cancel stuck tasks), matching the orchestrator tick-loop description:

        gather completed → reap stuck → fill empty slots up to N

    Args:
        tasks: A list of :class:`asyncio.Task` objects already scheduled via
            ``asyncio.create_task``.  Passing an empty list returns ``[]``
            immediately without blocking.
        timeout: Optional per-gather wall-clock limit in seconds.  When set,
            any task still running at the deadline is cancelled.  When
            ``None`` (default), no deadline is enforced and the call waits
            for all tasks unconditionally.

    Returns:
        A list of dicts — one per task — in task-list order::

            {
                "task":    asyncio.Task,   # the original task
                "success": bool,
                "result":  Any,            # task return value on success
                "error":   str | None,     # str(exc) on failure, else None
            }

        A reaped (timed-out) task has ``success=False`` and
        ``error="timeout"``.

    Raises:
        ValueError: If *timeout* is provided and is not positive.
    """
    if not tasks:
        return []

    if timeout is not None and timeout <= 0:
        raise ValueError(
            f"timeout must be positive when provided; got {timeout!r}"
        )

    if timeout is not None:
        done, pending = await asyncio.wait(
            tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED,
        )
        # Reap any tasks that are still running after the timeout.
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    else:
        done = set(tasks)
        pending = set()
        await asyncio.gather(*tasks, return_exceptions=True)

    results: list[dict[str, object]] = []
    for task in tasks:
        if task in pending:
            # Was reaped due to timeout.
            results.append(
                {
                    "task": task,
                    "success": False,
                    "result": None,
                    "error": "timeout",
                }
            )
            continue
        exc = task.exception() if not task.cancelled() else None
        if task.cancelled():
            results.append(
                {
                    "task": task,
                    "success": False,
                    "result": None,
                    "error": "cancelled",
                }
            )
        elif exc is not None:
            results.append(
                {
                    "task": task,
                    "success": False,
                    "result": None,
                    "error": str(exc),
                }
            )
        else:
            results.append(
                {
                    "task": task,
                    "success": True,
                    "result": task.result(),
                    "error": None,
                }
            )
    return results


__all__ = ["dispatch_concurrent_features", "gather_and_reap"]
