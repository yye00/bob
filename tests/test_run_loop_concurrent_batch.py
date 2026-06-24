"""Integration tests for concurrent batch building in bob3.run_loop.

Verifies that:
- claim_first_feature and claim_first_feature_before_batch_building are importable
  from bob3.run_loop (integration: bob3.run_loop AC).
- The core fix works: batch[0] is claimed as 'executing' before the loop, so the
  batch grows to min(N, max_concurrent_features) rather than staying at size 1.
- Integration with the module-level __all__ and the alias relationship.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from bob3.run_loop import (
    claim_first_feature,
    claim_first_feature_before_batch_building,
)


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
# Integration: importability from bob3.run_loop
# ---------------------------------------------------------------------------


def test_claim_first_feature_importable_from_run_loop():
    """claim_first_feature is importable from bob3.run_loop."""
    assert callable(claim_first_feature)


def test_claim_first_feature_before_batch_building_importable_from_run_loop():
    """claim_first_feature_before_batch_building is importable from bob3.run_loop."""
    assert callable(claim_first_feature_before_batch_building)


def test_claim_first_feature_is_alias_for_before_batch_building():
    """claim_first_feature and claim_first_feature_before_batch_building produce identical results."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    f3 = FakeFeature(id="feat-3")

    store_a = FakeStore([f1, f2, f3])
    store_b = FakeStore([FakeFeature(id="feat-1"), FakeFeature(id="feat-2"), FakeFeature(id="feat-3")])

    result_a = claim_first_feature(
        first_feature=f1,
        max_concurrent_features=3,
        find_next_ready_feature=store_a.find_next_ready_feature,
        update_feature=store_a.update_feature,
    )
    result_b = claim_first_feature_before_batch_building(
        first_feature=FakeFeature(id="feat-1"),
        max_concurrent_features=3,
        find_next_ready_feature=store_b.find_next_ready_feature,
        update_feature=store_b.update_feature,
    )

    assert len(result_a) == len(result_b)
    assert [f.id for f in result_a] == [f.id for f in result_b]


# ---------------------------------------------------------------------------
# Core regression fix: concurrent batch fills beyond size 1
# ---------------------------------------------------------------------------


def test_concurrent_batch_fills_with_8_wide_cap_and_19_features():
    """Regression: 8-wide cap + 19 ready features → batch size 8, not 1.

    This is the bob66 root-cause scenario. Before the fix, batch stayed at 1.
    """
    features = [FakeFeature(id=f"feat-{i:02d}") for i in range(19)]
    store = FakeStore(features)

    batch = claim_first_feature(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 8, (
        f"Expected batch size 8 with 8-wide cap and 19 features, got {len(batch)}"
    )


def test_first_feature_claimed_before_loop_so_second_is_different():
    """batch[0] is claimed before the loop; find() returns a different feature for slot 2."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = claim_first_feature(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 2
    assert batch[0].id == "feat-1"
    assert batch[1].id == "feat-2"


def test_all_batch_members_marked_executing_before_return():
    """All features in the returned batch have been marked 'executing'."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(5)]
    store = FakeStore(features)

    batch = claim_first_feature(
        first_feature=features[0],
        max_concurrent_features=5,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    claimed_ids = {fid for fid, status in store.update_calls if status == "executing"}
    batch_ids = {f.id for f in batch}
    assert batch_ids == claimed_ids


def test_no_duplicate_features_in_batch():
    """Each feature appears at most once in the returned batch."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(10)]
    store = FakeStore(features)

    batch = claim_first_feature(
        first_feature=features[0],
        max_concurrent_features=10,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    ids = [f.id for f in batch]
    assert len(ids) == len(set(ids)), f"Duplicate IDs in batch: {ids}"


# ---------------------------------------------------------------------------
# Sequential path: max_concurrent_features <= 1
# ---------------------------------------------------------------------------


def test_sequential_path_returns_single_feature_no_db_writes():
    """max_concurrent_features=1 → [first_feature] with no update calls."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = claim_first_feature(
        first_feature=f1,
        max_concurrent_features=1,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert batch == [f1]
    assert store.update_calls == []


# ---------------------------------------------------------------------------
# Batch size respects both cap and availability
# ---------------------------------------------------------------------------


def test_batch_capped_at_max_concurrent_features():
    """Batch never exceeds max_concurrent_features even if more features are ready."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(20)]
    store = FakeStore(features)

    batch = claim_first_feature(
        first_feature=features[0],
        max_concurrent_features=6,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 6


def test_batch_size_equals_available_when_fewer_than_cap():
    """When fewer features available than cap, batch == available count."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(3)]
    store = FakeStore(features)

    batch = claim_first_feature(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 3


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_none_first_feature_raises():
    """None first_feature raises ValueError."""
    with pytest.raises(ValueError, match="first_feature"):
        claim_first_feature(
            first_feature=None,
            max_concurrent_features=4,
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )


def test_none_find_next_raises():
    """None find_next_ready_feature raises TypeError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        claim_first_feature(
            first_feature=f1,
            max_concurrent_features=4,
            find_next_ready_feature=None,  # type: ignore[arg-type]
            update_feature=lambda fid, *, status: None,
        )


def test_none_update_feature_raises():
    """None update_feature raises TypeError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        claim_first_feature(
            first_feature=f1,
            max_concurrent_features=4,
            find_next_ready_feature=lambda: None,
            update_feature=None,  # type: ignore[arg-type]
        )


def test_non_integer_cap_raises():
    """Non-integer max_concurrent_features raises TypeError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        claim_first_feature(
            first_feature=f1,
            max_concurrent_features="eight",  # type: ignore[arg-type]
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )
