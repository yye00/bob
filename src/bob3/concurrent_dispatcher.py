"""Concurrent feature dispatcher for the Bob3 orchestrator.

Feature: Orchestrator dispatch concurrency — let multiple ready features run
in parallel instead of strict single-flight (01061cb6-8609-4ca2-9043-54aabe45d912).

Exports two primary functions:

:func:`dispatch_concurrent_features`
    Fill open concurrency slots with ready features and dispatch them as
    concurrent asyncio tasks.  Replaces the previous sequential
    ``result = await execute_feature(feature)`` call in the tick loop.

:func:`gather_completed_features`
    Collect outcomes from a list of asyncio tasks once they have completed,
    with failure isolation so one bad task does not cancel its peers.

Both functions delegate to proven implementations in
``bob3.orchestrator.run_loop`` and ``bob3.orchestrator.concurrent_executor``
to avoid duplicating logic.
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
    """Dispatch up to ``BOB3_MAX_CONCURRENT_FEATURES`` ready features concurrently.

    This wraps :func:`bob3.orchestrator.run_loop.dispatch_concurrent_features`
    to expose the function at the ``bob3.concurrent_dispatcher`` namespace as
    required by the feature ACs.

    The orchestrator tick loop becomes::

        results = await dispatch_concurrent_features(
            loop,
            worker=execute_feature,
            active_feature_ids=in_flight_ids,
        )

    which replaces the previous sequential
    ``result = await execute_feature(feature)``.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the concurrency cap
            (``loop.max_concurrent_features``).
        worker: Async callable ``async def worker(feature) -> result`` invoked
            for each claimed feature.  Failures are isolated per feature.
        active_feature_ids: Optional set of feature IDs already in flight.
            Claimed features are added before dispatch so that repeated calls
            within the same tick don't double-dispatch the same feature.
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
    from bob3.orchestrator.run_loop import (
        dispatch_concurrent_features as _dispatch,
    )
    return await _dispatch(
        loop,
        worker=worker,
        active_feature_ids=active_feature_ids,
        on_failure=on_failure,
    )


def fill_empty_slots(
    loop: Any,
    *,
    active_feature_ids: "set[str] | None" = None,
) -> "list[Any]":
    """Fill open concurrency slots with ready features from *loop*'s project.

    This wraps :func:`bob3.orchestrator.run_loop.dispatch_up_to_concurrency`
    to expose slot-filling at the ``bob3.concurrent_dispatcher`` namespace as
    required by the feature ACs.

    Queries the database for features in ``ready`` status, skipping any already
    in ``active_feature_ids``, until the concurrency cap is reached or no more
    ready features are available.  Each claimed feature is marked ``executing``
    in the database before being returned.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the concurrency cap
            (``loop.max_concurrent_features``).
        active_feature_ids: Optional set of feature IDs already in flight.
            Features whose IDs are in this set are skipped even if the
            database would return them.

    Returns:
        List of :class:`~bob3.models.Feature` objects that were claimed and
        should be dispatched as concurrent tasks.  May be empty when there are
        no ready features or when the cap is already saturated.

    Raises:
        ValueError: If *loop* is ``None``.
    """
    if loop is None:
        raise ValueError("loop must not be None")
    from bob3.orchestrator.run_loop import dispatch_up_to_concurrency
    return dispatch_up_to_concurrency(loop, active_feature_ids=active_feature_ids)


async def gather_completed_features(
    tasks: "list[asyncio.Task[object]]",
) -> "list[dict[str, object]]":
    """Collect outcomes from a list of asyncio tasks, with failure isolation.

    Awaits all *tasks* via :func:`asyncio.gather` with ``return_exceptions=True``
    so a failing task never propagates its exception to callers and all tasks
    always run to completion.

    This wraps :func:`bob3.orchestrator.run_loop.gather_completed_dispatches`
    to expose the function at the ``bob3.concurrent_dispatcher`` namespace as
    required by the feature ACs.

    Args:
        tasks: A list of :class:`asyncio.Task` objects already scheduled via
            ``asyncio.create_task``.  Passing an empty list returns ``[]``
            immediately without blocking.

    Returns:
        A list of dicts — one per task — in task-list order::

            {
                "task":    asyncio.Task,
                "success": bool,
                "result":  Any,         # task return value on success
                "error":   str | None,  # str(exc) on failure, else None
            }
    """
    from bob3.orchestrator.run_loop import (
        gather_completed_dispatches as _gather,
    )
    return await _gather(tasks)


# AC alias: "Function defined: bob3.concurrent_dispatcher.gather_completed_tasks"
gather_completed_tasks = gather_completed_features


__all__ = [
    "dispatch_concurrent_features",
    "fill_empty_slots",
    "gather_completed_features",
    "gather_completed_tasks",
]
