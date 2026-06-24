"""Tests for concurrent_batch_builder_must_claim_first_feature_executing.

Verifies that the concurrent batch builder:
1. Claims batch[0] as 'executing' BEFORE the batch-building loop.
2. Returns min(N, max_concurrent_features) features when N are available.
3. Returns size-1 batch when only one feature is claimable.
4. Returns [first_feature] immediately when max_concurrent_features == 1.
5. Never adds the same feature twice (dedup guard).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from bob3.concurrent_batch_builder_must_claim_first_feature_executing import (
    concurrent_batch_builder_must_claim_first_feature_executing,
)


@dataclass
class FakeFeature:
    id: str
    status: str = "ready"


class FakeStore:
    """Simulates DB-backed feature store with status tracking."""

    def __init__(self, features: list[FakeFeature]) -> None:
        self._features: dict[str, FakeFeature] = {f.id: f for f in features}
        self.update_calls: list[tuple[str, str]] = []

    def update_feature(self, feature_id: str, *, status: str) -> None:
        self.update_calls.append((feature_id, status))
        if feature_id in self._features:
            self._features[feature_id].status = status

    def find_next_ready_feature(self) -> FakeFeature | None:
        for feat in self._features.values():
            if feat.status == "ready":
                return feat
        return None


# ---------------------------------------------------------------------------
# Module and function existence (AC: pytest + Function defined)
# ---------------------------------------------------------------------------


def test_concurrent_batch_builder_must_claim_first_feature_executing():
    """AC-named test: function exists, is callable, and correct claiming behaviour.

    With 2 claimable features and cap=2, the returned batch must be size 2,
    proving that batch[0] was claimed before the loop (else the loop would
    return batch[0] again and stop at size 1).
    """
    f1 = FakeFeature(id="ac-feat-1")
    f2 = FakeFeature(id="ac-feat-2")
    store = FakeStore([f1, f2])

    assert callable(concurrent_batch_builder_must_claim_first_feature_executing)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 2
    assert batch[0].id == "ac-feat-1"
    assert batch[1].id == "ac-feat-2"


def test_concurrent_batch_builder_must_claim_first_feature_executing_importable():
    """Function is importable from the module."""
    assert callable(concurrent_batch_builder_must_claim_first_feature_executing)


# ---------------------------------------------------------------------------
# Core behaviour: first feature must be claimed before batch-building loop
# ---------------------------------------------------------------------------


def test_first_feature_claimed_before_loop_runs():
    """batch[0] is claimed 'executing' before find_next_ready_feature is called.

    Simulates the bob66 defect: if batch[0] is NOT claimed first, the loop
    returns it again and the batch stays size 1.  With the fix, the loop finds
    a second feature.
    """
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 2
    assert batch[0].id == "feat-1"
    assert batch[1].id == "feat-2"


def test_first_feature_status_set_to_executing_before_second_query():
    """update_feature(batch[0], executing) is called before the first loop iteration."""
    claimed_order: list[str] = []
    find_calls: list[int] = [0]

    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    original_update = store.update_feature
    def tracking_update(fid: str, *, status: str) -> None:
        claimed_order.append(fid)
        original_update(fid, status=status)

    original_find = store.find_next_ready_feature
    def tracking_find() -> FakeFeature | None:
        find_calls[0] += 1
        # By the time we are called for the first time, feat-1 must already
        # be in the claimed_order list (claimed before we were invoked).
        if find_calls[0] == 1:
            assert "feat-1" in claimed_order, (
                "batch[0] must be claimed before find_next_ready_feature() runs"
            )
        return original_find()

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=tracking_find,
        update_feature=tracking_update,
    )

    assert len(batch) == 2
    assert find_calls[0] >= 1


# ---------------------------------------------------------------------------
# Batch size limits
# ---------------------------------------------------------------------------


def test_batch_size_capped_at_max_concurrent_features():
    """Batch never exceeds max_concurrent_features even if more features are ready."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(10)]
    store = FakeStore(features)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=features[0],
        max_concurrent_features=4,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 4


def test_batch_size_equals_available_when_fewer_than_cap():
    """Batch size == N when N claimable features < max_concurrent_features."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(3)]
    store = FakeStore(features)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 3


def test_batch_size_1_when_only_one_feature_claimable():
    """When only one feature exists the batch is size 1 (boundary condition)."""
    f1 = FakeFeature(id="only-feat")
    store = FakeStore([f1])

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=f1,
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 1
    assert batch[0].id == "only-feat"


def test_sequential_path_when_max_concurrent_is_1():
    """When max_concurrent_features == 1, return [first_feature] with no DB writes."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=f1,
        max_concurrent_features=1,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 1
    assert batch[0].id == "feat-1"
    # No DB writes in sequential path
    assert store.update_calls == []


# ---------------------------------------------------------------------------
# Dedup guard: no feature appears twice
# ---------------------------------------------------------------------------


def test_no_duplicate_features_in_batch():
    """Each feature appears at most once in the returned batch."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(5)]
    store = FakeStore(features)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    ids = [f.id for f in batch]
    assert len(ids) == len(set(ids)), f"Duplicates found: {ids}"


# ---------------------------------------------------------------------------
# All batch members claimed as 'executing'
# ---------------------------------------------------------------------------


def test_all_batch_members_marked_executing():
    """Every feature in the batch has been marked 'executing' before return."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(4)]
    store = FakeStore(features)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=features[0],
        max_concurrent_features=4,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    claimed_ids = {fid for fid, status in store.update_calls if status == "executing"}
    batch_ids = {f.id for f in batch}
    assert batch_ids == claimed_ids, (
        f"Not all batch members were claimed: batch={batch_ids}, claimed={claimed_ids}"
    )


# ---------------------------------------------------------------------------
# find_next_ready_feature returning None stops the loop
# ---------------------------------------------------------------------------


def test_loop_stops_when_find_returns_none():
    """Batch building stops immediately when find_next_ready_feature returns None."""
    f1 = FakeFeature(id="feat-1")
    call_count = [0]

    def find_none() -> FakeFeature | None:
        call_count[0] += 1
        return None

    updates: list[tuple[str, str]] = []

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=f1,
        max_concurrent_features=5,
        find_next_ready_feature=find_none,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    assert len(batch) == 1
    assert batch[0].id == "feat-1"
    assert call_count[0] == 1  # Called once, returned None, loop exited


# ---------------------------------------------------------------------------
# Regression: bob66 sequential-despite-8-wide-cap scenario
# ---------------------------------------------------------------------------


def test_bob66_regression_19_claimable_8_cap():
    """Regression: 19 claimable features with 8-wide cap yields batch of 8.

    Reproduces the bob66 failure mode where strictly sequential execution
    was observed despite max_concurrent_features=8 and 19 ready features.
    """
    features = [FakeFeature(id=f"feat-{i:02d}") for i in range(19)]
    store = FakeStore(features)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 8, (
        f"Expected batch size 8 with 19 claimable features and cap=8, got {len(batch)}"
    )


def test_bob66_regression_all_batch_members_are_distinct():
    """All 8 features in the batch are distinct (no bob66-style duplication)."""
    features = [FakeFeature(id=f"feat-{i:02d}") for i in range(19)]
    store = FakeStore(features)

    batch = concurrent_batch_builder_must_claim_first_feature_executing(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    ids = [f.id for f in batch]
    assert len(set(ids)) == 8
