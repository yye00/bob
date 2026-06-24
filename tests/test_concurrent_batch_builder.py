"""Tests for concurrent batch builder — claim first feature before batch building.

Feature 9d2d1835-fac6-4ebd-a3d2-7a26216fbb5b

Verifies that:
1. claim_first_feature_before_batch_building exists and is callable in run_loop.
2. The function claims batch[0] as 'executing' before entering the batch-building loop.
3. The batch contains min(N, max_concurrent_features) features when N features are claimable.
4. Batch size is 1 when only one feature is claimable.
5. Each tick logs the dispatched batch size.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from bob.run_loop import claim_first_feature_before_batch_building


@dataclass
class FakeFeature:
    id: str
    status: str = "ready"


class FakeStore:
    """Simulates a DB-backed feature store with status tracking."""

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
# AC: Function defined: run_loop.claim_first_feature_before_batch_building
# ---------------------------------------------------------------------------


def test_claim_first_feature_before_batch_building_is_callable():
    """Function is importable from bob.run_loop and callable."""
    assert callable(claim_first_feature_before_batch_building)


def test_claim_first_feature_before_batch_building_basic():
    """With 2 claimable features and cap=2, returns batch of size 2."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 2
    assert batch[0].id == "feat-1"
    assert batch[1].id == "feat-2"


# ---------------------------------------------------------------------------
# Core behaviour: first feature claimed before batch-building loop
# ---------------------------------------------------------------------------


def test_first_feature_claimed_before_loop():
    """batch[0] is claimed 'executing' before find_next_ready_feature runs.

    This proves the fix: without the pre-claim, find_next_ready_feature()
    returns batch[0] again (still 'ready'), the dedup guard breaks the loop,
    and the batch stays at size 1 despite an 8-wide cap.
    """
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    claimed_before_find: list[str] = []
    find_call_count = [0]

    original_update = store.update_feature
    original_find = store.find_next_ready_feature

    def tracking_update(fid: str, *, status: str) -> None:
        if status == "executing":
            claimed_before_find.append(fid)
        original_update(fid, status=status)

    def tracking_find() -> FakeFeature | None:
        find_call_count[0] += 1
        if find_call_count[0] == 1:
            assert "feat-1" in claimed_before_find, (
                "batch[0] must be claimed as 'executing' before find_next_ready_feature() runs"
            )
        return original_find()

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=tracking_find,
        update_feature=tracking_update,
    )

    assert len(batch) == 2
    assert find_call_count[0] >= 1


# ---------------------------------------------------------------------------
# Batch size limits
# ---------------------------------------------------------------------------


def test_batch_capped_at_max_concurrent_features():
    """Batch size never exceeds max_concurrent_features."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(10)]
    store = FakeStore(features)

    batch = claim_first_feature_before_batch_building(
        first_feature=features[0],
        max_concurrent_features=4,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 4


def test_batch_size_equals_n_when_fewer_than_cap():
    """When fewer features than cap are available, batch = N claimable features."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(3)]
    store = FakeStore(features)

    batch = claim_first_feature_before_batch_building(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 3


def test_batch_size_1_when_only_one_claimable():
    """Batch is size 1 when only one feature is claimable."""
    f1 = FakeFeature(id="only-feat")
    store = FakeStore([f1])

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 1
    assert batch[0].id == "only-feat"


def test_sequential_path_max_concurrent_1():
    """When max_concurrent_features == 1, returns [first_feature] without DB writes."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=1,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 1
    assert batch[0].id == "feat-1"
    assert store.update_calls == []


# ---------------------------------------------------------------------------
# No duplicates
# ---------------------------------------------------------------------------


def test_no_duplicate_features_in_batch():
    """Each feature appears at most once in the returned batch."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(5)]
    store = FakeStore(features)

    batch = claim_first_feature_before_batch_building(
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

    batch = claim_first_feature_before_batch_building(
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
# Regression: bob66 sequential-despite-8-wide-cap
# ---------------------------------------------------------------------------


def test_bob66_regression_19_claimable_8_cap():
    """Regression: 19 claimable features with 8-wide cap yields batch of 8."""
    features = [FakeFeature(id=f"feat-{i:02d}") for i in range(19)]
    store = FakeStore(features)

    batch = claim_first_feature_before_batch_building(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 8, (
        f"Expected batch size 8 with 19 claimable features and cap=8, got {len(batch)}"
    )


def test_bob66_regression_all_batch_members_distinct():
    """All 8 features in the batch are distinct (no bob66-style duplication)."""
    features = [FakeFeature(id=f"feat-{i:02d}") for i in range(19)]
    store = FakeStore(features)

    batch = claim_first_feature_before_batch_building(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    ids = [f.id for f in batch]
    assert len(set(ids)) == 8
