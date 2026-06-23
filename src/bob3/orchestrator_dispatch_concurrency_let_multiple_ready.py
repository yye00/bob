"""Orchestrator concurrent dispatch — let multiple ready features run in parallel.

Feature 8a4d3ac6-d557-41ed-ade0-08b2f11c9271

Addresses the single-hung-subagent-blocks-round failure mode: previously the
orchestrator awaited one feature at a time (synchronous await per feature),
so a single bad-actor feature could hold the entire round hostage even after
its watchdog cancelled it.

Fix: ``BOB3_MAX_CONCURRENT_FEATURES`` (default 3) bounds how many ready
features may be dispatched as concurrent asyncio tasks.  Each task carries its
own watchdog; one hung feature cannot block its peers.

The orchestrator tick loop becomes::

    results = await orchestrator_dispatch_concurrency_let_multiple_ready(
        loop,
        worker=execute_feature,
        active_feature_ids=in_flight_ids,
    )

which replaces the previous sequential single-feature await.

Exports
-------
orchestrator_dispatch_concurrency_let_multiple_ready
    Primary entry point: claim + dispatch up to N ready features concurrently.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from bob3 import db
from bob3.orchestrator.concurrent_executor import run_concurrent

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT = 3

__all__ = ["orchestrator_dispatch_concurrency_let_multiple_ready"]


def _resolve_concurrency_cap() -> int:
    raw = os.environ.get("BOB3_MAX_CONCURRENT_FEATURES")
    if raw is None:
        return _DEFAULT_MAX_CONCURRENT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_MAX_CONCURRENT_FEATURES=%r; using default %d",
            raw,
            _DEFAULT_MAX_CONCURRENT,
        )
        return _DEFAULT_MAX_CONCURRENT
    if value < 1:
        logger.warning(
            "Non-positive BOB3_MAX_CONCURRENT_FEATURES=%r; clamping to 1",
            raw,
        )
        return 1
    return value


def _claim_ready_features(
    loop: Any,
    *,
    active_feature_ids: set[str],
) -> list[Any]:
    """Fill open slots up to loop.max_concurrent_features with ready features.

    Each claimed feature is immediately marked ``executing`` in the DB so that
    a concurrent caller or subsequent tick does not re-select it.
    """
    cap = loop.max_concurrent_features
    open_slots = max(0, cap - len(active_feature_ids))
    if open_slots <= 0:
        return []

    claimed: list[Any] = []
    seen_ids: set[str] = set(active_feature_ids)

    for _ in range(open_slots):
        feature = loop.find_next_ready_feature()
        if feature is None:
            break
        if feature.id in seen_ids:
            break
        seen_ids.add(feature.id)
        db.update_feature(feature.id, status="executing")
        claimed.append(feature)

    return claimed


async def orchestrator_dispatch_concurrency_let_multiple_ready(
    loop: Any,
    *,
    worker: Any,
    active_feature_ids: set[str] | None = None,
    on_failure: Any = None,
) -> list[dict[str, object]]:
    """Dispatch up to ``BOB3_MAX_CONCURRENT_FEATURES`` ready features concurrently.

    Combines slot-filling + DB claim with bounded-concurrency gather (failure
    isolation per feature) into a single awaitable call.  A crash in one worker
    never cancels its peers; every feature runs to completion or error
    independently.

    Args:
        loop: The :class:`~bob3.orchestrator.run_loop.OrchestrationLoop`
            providing project context and the ``max_concurrent_features`` cap.
        worker: Async callable ``async def worker(feature) -> result`` invoked
            for each claimed feature.
        active_feature_ids: Feature IDs already in flight.  Claimed features
            are excluded from this set to avoid double-dispatch within a tick.
        on_failure: Optional callback ``on_failure(feature, exc)`` invoked after
            each worker failure.  Any exception raised by the callback is
            swallowed to preserve failure isolation of sibling features.

    Returns:
        List of result dicts — one per dispatched feature::

            {
                "feature_id": str,
                "success":    bool,
                "result":     Any,
                "error":      str | None,
            }

        Returns an empty list when the cap is saturated or no ready features exist.
    """
    if active_feature_ids is None:
        active_feature_ids = set()

    claimed = _claim_ready_features(loop, active_feature_ids=active_feature_ids)
    if not claimed:
        return []

    max_concurrent = _resolve_concurrency_cap()
    return await run_concurrent(
        claimed,
        worker=worker,
        max_concurrent=max_concurrent,
        on_failure=on_failure,
    )
