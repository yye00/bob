"""Concurrent batch builder — claim first feature executing before re-querying.

Feature 57376148-4380-4f0d-aadd-40d19678b93c

Root cause (bob66)
------------------
The orchestrator ran with max_concurrent_features=8 and 19 claimable features yet
dispatched strictly one feature at a time (~9 min/feature). The concurrent-dispatch
branch seeded batch=[feature] then entered a while loop calling find_next_ready_feature()
to fill remaining slots. Each *additional* feature was immediately claimed as
status='executing', but batch[0] was never claimed before the loop ran. Its status
stayed 'ready' so the very first find_next_ready_feature() call returned it again
(highest priority, still 'ready'). The dedup guard broke the loop immediately →
batch size 1 → sequential execution despite the 8-wide cap.

Fix
---
Claim batch[0] as status='executing' BEFORE entering the batch-building while loop.
This removes it from the features_ready view so the next find_next_ready_feature()
returns the second-priority feature, letting the batch grow to max_concurrent_features.
execute_feature re-writes status='executing' later — the early claim is idempotent.

Behaviour guarantees
--------------------
- WHEN max_concurrent_features > 1 AND N features are claimable,
  the dispatched batch contains min(N, max_concurrent_features) features.
- WHEN exactly one feature is claimable the batch is size 1 (sequential, unchanged).
- Each tick logs the dispatched batch size for concurrency-saturation observability.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = ["concurrent_batch_builder_must_claim_first_feature_executing"]


def concurrent_batch_builder_must_claim_first_feature_executing(
    *,
    first_feature: Any,
    max_concurrent_features: int,
    find_next_ready_feature: Callable[[], Optional[Any]],
    update_feature: Callable[..., None],
) -> list[Any]:
    """Build a concurrent execution batch with correct first-feature claiming.

    Ensures batch[0] is claimed as 'executing' BEFORE the batch-building loop so
    that subsequent find_next_ready_feature() calls never return it again.

    Parameters
    ----------
    first_feature:
        The first feature to execute (already selected by the orchestrator tick).
        Must have an ``.id`` attribute.
    max_concurrent_features:
        Maximum batch size.  Must be >= 1.  When 1, returns [first_feature]
        immediately (sequential path — no claiming or looping needed).
    find_next_ready_feature:
        Callable returning the next highest-priority ready feature or None.
        Called repeatedly until the batch is full or no more features remain.
    update_feature:
        Callable used to mark a feature as 'executing' in the backing store.
        Signature: ``update_feature(feature_id, status='executing')``.

    Returns
    -------
    list
        Batch of features to dispatch, length in [1, max_concurrent_features].
        All features in the batch (including first_feature) have been marked
        'executing' in the backing store before this function returns.
    """
    if max_concurrent_features <= 1:
        return [first_feature]

    batch: list[Any] = [first_feature]

    # CRITICAL FIX: claim batch[0] BEFORE querying for additional features.
    # Without this, find_next_ready_feature() returns first_feature again
    # (status still 'ready', highest priority) and the dedup guard kills
    # the loop — batch stays size 1, execution is strictly sequential.
    update_feature(first_feature.id, status="executing")

    remaining_slots = max_concurrent_features - 1
    seen_ids: set[str] = {first_feature.id}

    while remaining_slots > 0:
        next_feat = find_next_ready_feature()
        if next_feat is None:
            break
        if next_feat.id in seen_ids:
            break
        seen_ids.add(next_feat.id)
        update_feature(next_feat.id, status="executing")
        batch.append(next_feat)
        remaining_slots -= 1

    logger.info(
        "CONCURRENT_BATCH_DISPATCHED size=%d cap=%d",
        len(batch),
        max_concurrent_features,
    )
    return batch
