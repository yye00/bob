"""Concurrent feature executor with failure isolation (feature 6e085356).

Provides :func:`run_concurrent`, a drop-in replacement for the
single-feature await in :mod:`bob3.orchestrator.run_loop`.  It dispatches
up to *N* features concurrently using :func:`asyncio.gather` + a
:class:`asyncio.Semaphore`.

Key guarantees
--------------
* A failure in one worker is **never** propagated to peers — each feature
  runs inside its own ``try/except`` that catches :class:`BaseException`.
* The ``on_failure`` callback (if provided) is invoked synchronously after
  each failure; an exception raised by the callback is swallowed so it
  cannot break the loop.
* ``max_concurrent=1`` (the default) reproduces the previous sequential
  behaviour exactly and is safe to use as the default for backward
  compatibility.
* All results are collected and returned in an unordered list of dicts;
  callers should not rely on order when ``max_concurrent > 1``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F")

# Type aliases
WorkerCallable = Callable[[Any], Awaitable[Any]]
OnFailureCallable = Callable[[Any, Exception], None]

WorkerResult = dict[str, Any]


async def run_concurrent(
    features: list[Any],
    *,
    worker: WorkerCallable,
    max_concurrent: int = 1,
    on_failure: OnFailureCallable | None = None,
    per_task_timeout: float | None = None,
) -> list[WorkerResult]:
    """Dispatch *features* to *worker* with bounded concurrency.

    Each feature is dispatched as a separate asyncio task.  At most
    ``max_concurrent`` tasks run simultaneously; additional tasks wait on an
    internal :class:`asyncio.Semaphore` before acquiring a slot.

    Args:
        features: Sequence of feature objects (duck-typed; only ``.id`` is
            accessed by this function, but *worker* may access any field).
        worker: An async callable ``async def worker(feature) -> result``.
            It MUST be coroutine-returning; wrapping a sync function with
            ``asyncio.to_thread`` is the caller's responsibility.
        max_concurrent: Maximum number of workers that may execute
            simultaneously.  ``1`` (the default) gives sequential behaviour.
            Values < 1 are silently clamped to 1.
        on_failure: Optional callback invoked ``on_failure(feature, exc)``
            after each failing worker.  Called synchronously from the
            gathering task; any exception it raises is caught and logged so
            it cannot contaminate sibling features.

    Returns:
        A list of result dicts, one per input feature::

            {
                "feature_id": str,   # feature.id
                "success":   bool,
                "result":    Any,    # worker return value, or None on failure
                "error":     str | None,  # str(exc) on failure, else None
            }

        The list may be in any order when ``max_concurrent > 1``.
    """
    if not features:
        return []

    limit = max(1, int(max_concurrent))
    sem = asyncio.Semaphore(limit)
    results: list[WorkerResult] = []

    async def _run_one(feature: Any) -> None:
        feature_id = getattr(feature, "id", repr(feature))
        async with sem:
            try:
                # Bound each worker so a silently-dead subagent cannot hang the
                # whole gather forever. Without this, the concurrent path awaited
                # execute_feature with NO timeout (only the inner research spawn
                # was wrapped), so when a feature's claude subagent died its
                # status stayed 'executing' and the gather never returned →
                # main loop blocked in ep_poll → the stuck-executing reaper never
                # ran → 3+ features wedged 60-75 min (bob72). On timeout we raise
                # TimeoutError, which the except below turns into a normal worker
                # failure (on_failure releases the reservation; the reaper then
                # resets the row to 'ready' on the next tick).
                if per_task_timeout and per_task_timeout > 0:
                    result = await asyncio.wait_for(worker(feature), timeout=per_task_timeout)
                else:
                    result = await worker(feature)
                results.append(
                    {
                        "feature_id": feature_id,
                        "success": True,
                        "result": result,
                        "error": None,
                    }
                )
            except BaseException as exc:
                error_msg = str(exc)
                logger.warning(
                    "Concurrent worker failed for feature %s: %s",
                    feature_id,
                    error_msg,
                    exc_info=True,
                )
                results.append(
                    {
                        "feature_id": feature_id,
                        "success": False,
                        "result": None,
                        "error": error_msg,
                    }
                )
                if on_failure is not None:
                    try:
                        on_failure(feature, exc)
                    except Exception as cb_exc:
                        logger.warning(
                            "on_failure callback raised for feature %s: %s",
                            feature_id,
                            cb_exc,
                        )

    await asyncio.gather(*(_run_one(f) for f in features))
    return results


__all__ = ["run_concurrent"]
