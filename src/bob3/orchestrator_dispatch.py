"""Orchestrator concurrent dispatch — feature f9de5db3.

Provides :func:`dispatch_concurrent_features`, the primary entry-point for
dispatching up to ``BOB3_MAX_CONCURRENT_FEATURES`` (default 3) ready features
as concurrent asyncio tasks.

The orchestrator tick loop replaces the previous sequential single-feature
await with::

    results = await dispatch_concurrent_features(
        loop,
        worker=execute_feature,
        active_feature_ids=in_flight_ids,
    )

Failure isolation guarantees that a crash in one feature worker never cancels
peers; every feature runs to completion (or error) independently.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from typing import TYPE_CHECKING, Any, Optional

from bob3 import db

if TYPE_CHECKING:
    from bob3.orchestrator.run_loop import OrchestrationLoop

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT_FEATURES = 3


@dataclasses.dataclass
class ConcurrentFeatureSlot:
    """Tracks a single in-flight feature during concurrent dispatch.

    Each slot is created when a feature is claimed and dispatched as an
    asyncio task.  The orchestrator tick loop uses a list of these to
    determine which slots are still running and which have completed.

    Attributes:
        feature_id: ID of the claimed feature.
        task: The asyncio.Task running the feature worker, or None before
            dispatch begins.
        success: True if the worker completed without error; None while
            still in flight.
        result: The return value of the worker on success; None otherwise.
        error: String representation of the exception on failure; None
            on success or while still in flight.
    """

    feature_id: str
    task: Optional[asyncio.Task] = dataclasses.field(default=None, repr=False)
    success: Optional[bool] = None
    result: Any = None
    error: Optional[str] = None

    def is_done(self) -> bool:
        """Return True when the slot's task has completed (success or failure)."""
        return self.success is not None

    def is_running(self) -> bool:
        """Return True when the task is still in flight."""
        return self.task is not None and not self.is_done()


def resolve_max_concurrent_features() -> int:
    """Return the concurrency cap from the environment.

    Reads ``BOB3_MAX_CONCURRENT_FEATURES``; falls back to 3 on parse errors
    or non-positive values.
    """
    raw = os.environ.get("BOB3_MAX_CONCURRENT_FEATURES")
    if raw is None:
        return _DEFAULT_MAX_CONCURRENT_FEATURES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_MAX_CONCURRENT_FEATURES=%r; using default %d",
            raw,
            _DEFAULT_MAX_CONCURRENT_FEATURES,
        )
        return _DEFAULT_MAX_CONCURRENT_FEATURES
    if value < 1:
        logger.warning(
            "Non-positive BOB3_MAX_CONCURRENT_FEATURES=%r; clamping to 1",
            raw,
        )
        return 1
    return value


def open_dispatch_slots(
    loop: "OrchestrationLoop",
    *,
    active_feature_ids: "set[str] | None" = None,
) -> int:
    """Return the number of additional dispatch slots available on *loop*.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            whose ``max_concurrent_features`` cap to check.
        active_feature_ids: Optional set of feature IDs currently in flight.
            When supplied, open slots = cap - len(active_feature_ids).
            When ``None``, the full cap is returned.

    Returns:
        Non-negative integer; 0 means the cap is saturated.
    """
    cap = loop.max_concurrent_features
    if active_feature_ids is None:
        return max(0, cap)
    return max(0, cap - len(active_feature_ids))


def claim_ready_features(
    loop: "OrchestrationLoop",
    *,
    active_feature_ids: "set[str] | None" = None,
) -> list[Any]:
    """Claim up to *N* ready features from *loop*'s project, marking them executing.

    Fills open slots (``open_dispatch_slots``) by querying the database for
    ``ready`` features, skipping any in *active_feature_ids*.  Each claimed
    feature is immediately marked ``executing`` so concurrent callers don't
    re-select it.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the concurrency cap.
        active_feature_ids: Set of feature IDs already in flight.

    Returns:
        List of :class:`~bob3.models.Feature` objects ready to dispatch.
        May be empty when there are no ready features or the cap is saturated.
    """
    if active_feature_ids is None:
        active_feature_ids = set()

    slots = open_dispatch_slots(loop, active_feature_ids=active_feature_ids)
    if slots <= 0:
        return []

    claimed: list[Any] = []
    seen_ids: set[str] = set(active_feature_ids)

    for _ in range(slots):
        feature = loop.find_next_ready_feature()
        if feature is None:
            break
        if feature.id in seen_ids:
            break
        seen_ids.add(feature.id)
        db.update_feature(feature.id, status="executing")
        claimed.append(feature)

    return claimed


def fill_concurrent_slots(
    loop: "OrchestrationLoop",
    *,
    active_feature_ids: "set[str] | None" = None,
) -> list[Any]:
    """Fill open concurrent dispatch slots with ready features.

    Queries *loop*'s project for features in ``ready`` status, claiming up to
    ``open_dispatch_slots`` of them.  Each claimed feature is marked
    ``executing`` in the database so that a subsequent call (or a parallel
    caller) does not re-select the same feature.

    This is the canonical slot-filling primitive used by
    :func:`dispatch_concurrent_features`.  Callers that need only the
    slot-filling step without full dispatch can call this directly.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the concurrency cap.
        active_feature_ids: Set of feature IDs already in flight.
            Features whose IDs are in this set are skipped.  When ``None``,
            treated as an empty set.

    Returns:
        List of :class:`~bob3.models.Feature` objects that were claimed and
        are ready to be dispatched as concurrent tasks.  May be empty when
        there are no ready features or the cap is already saturated.
    """
    return claim_ready_features(loop, active_feature_ids=active_feature_ids)


async def dispatch_concurrent_features(
    loop: "OrchestrationLoop",
    *,
    worker: Any,
    active_feature_ids: "set[str] | None" = None,
    on_failure: Any = None,
) -> "list[dict[str, object]]":
    """Dispatch up to ``BOB3_MAX_CONCURRENT_FEATURES`` ready features concurrently.

    Combines :func:`claim_ready_features` (slot-filling + DB claim) with
    :func:`~bob3.orchestrator.concurrent_executor.run_concurrent` (bounded
    concurrency, failure isolation) into a single awaitable.

    Each feature runs in its own asyncio task with its own failure boundary;
    a crash in one worker never cancels peers.  The ``on_failure`` callback
    (if supplied) is invoked after each failing worker; any exception from the
    callback is swallowed.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the concurrency cap.
        worker: Async callable ``async def worker(feature) -> result`` invoked
            for each claimed feature.
        active_feature_ids: Feature IDs already in flight.  Claimed features
            are added to this set before dispatch so repeated calls in the
            same tick don't double-dispatch.
        on_failure: Optional callback ``on_failure(feature, exc)`` called after
            each worker failure.

    Returns:
        List of result dicts — one per dispatched feature::

            {
                "feature_id": str,
                "success":    bool,
                "result":     Any,
                "error":      str | None,
            }

        Empty when no slots are open or no ready features exist.
    """
    claimed = claim_ready_features(loop, active_feature_ids=active_feature_ids)
    if not claimed:
        return []
    # Lazy import to avoid circular dependency: bob3.orchestrator.__init__
    # imports from this module; importing concurrent_executor at module level
    # would re-enter bob3.orchestrator before it is fully initialised.
    from bob3.orchestrator.concurrent_executor import run_concurrent  # noqa: PLC0415
    max_concurrent = resolve_max_concurrent_features()
    return await run_concurrent(
        claimed,
        worker=worker,
        max_concurrent=max_concurrent,
        on_failure=on_failure,
    )


__all__ = [
    "ConcurrentFeatureSlot",
    "dispatch_concurrent_features",
    "fill_concurrent_slots",
    "claim_ready_features",
    "open_dispatch_slots",
    "resolve_max_concurrent_features",
]
