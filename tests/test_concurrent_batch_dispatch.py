"""Tests for concurrent_batch_dispatch in bob.run_loop.

Feature ee5b8637-a52c-47af-87ce-3dc857fa0040

Verifies that concurrent_batch_dispatch:
1. Is importable from bob.run_loop (integration AC).
2. Claims batch[0] as 'executing' BEFORE the batch-building loop.
3. Returns min(N, max_concurrent_features) features when N are available.
4. Returns size-1 batch when only one feature is claimable (boundary).
5. Raises ValueError for None first_feature (error path).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from bob.run_loop import concurrent_batch_dispatch


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
# AC: Function defined and importable from bob.run_loop (integration)
# ---------------------------------------------------------------------------


def test_concurrent_batch_dispatch_importable():
    """concurrent_batch_dispatch is importable from bob.run_loop."""
    assert callable(concurrent_batch_dispatch)


def test_concurrent_batch_dispatch_in_run_loop_module():
    """concurrent_batch_dispatch is a member of the bob.run_loop module."""
    import bob.run_loop as rl
    assert hasattr(rl, "concurrent_batch_dispatch")
    assert callable(rl.concurrent_batch_dispatch)


# ---------------------------------------------------------------------------
# Core behaviour: batch[0] claimed before batch-building loop
# ---------------------------------------------------------------------------


def test_concurrent_batch_dispatch_builds_full_batch():
    """With N claimable features and cap=N, batch is size N."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    batch = concurrent_batch_dispatch(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 2
    assert batch[0].id == "feat-1"
    assert batch[1].id == "feat-2"


def test_concurrent_batch_dispatch_first_feature_claimed_before_loop():
    """batch[0] is claimed executing before find_next_ready_feature() is called."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    store = FakeStore([f1, f2])

    claimed_before_find: list[bool] = []
    original_update = store.update_feature
    claimed_ids: list[str] = []

    def tracking_update(fid: str, *, status: str) -> None:
        claimed_ids.append(fid)
        original_update(fid, status=status)

    original_find = store.find_next_ready_feature
    find_call_count = [0]

    def tracking_find() -> FakeFeature | None:
        find_call_count[0] += 1
        if find_call_count[0] == 1:
            claimed_before_find.append("feat-1" in claimed_ids)
        return original_find()

    batch = concurrent_batch_dispatch(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=tracking_find,
        update_feature=tracking_update,
    )

    assert len(batch) == 2
    assert claimed_before_find == [True], (
        "batch[0] must be claimed executing before find_next_ready_feature is called"
    )


def test_concurrent_batch_dispatch_batch_capped_at_max():
    """Batch never exceeds max_concurrent_features even if more features exist."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(10)]
    store = FakeStore(features)

    batch = concurrent_batch_dispatch(
        first_feature=features[0],
        max_concurrent_features=4,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 4


def test_concurrent_batch_dispatch_size_1_when_one_claimable():
    """When only one feature is available, batch is size 1."""
    f1 = FakeFeature(id="only-feat")
    store = FakeStore([f1])

    batch = concurrent_batch_dispatch(
        first_feature=f1,
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 1
    assert batch[0].id == "only-feat"


def test_concurrent_batch_dispatch_sequential_path_no_side_effects():
    """With max_concurrent_features=1, no claiming or looping occurs."""
    f1 = FakeFeature(id="feat-1")
    updates: list = []
    find_calls = [0]

    def counting_find() -> FakeFeature | None:
        find_calls[0] += 1
        return None

    batch = concurrent_batch_dispatch(
        first_feature=f1,
        max_concurrent_features=1,
        find_next_ready_feature=counting_find,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    assert len(batch) == 1
    assert find_calls[0] == 0
    assert updates == []


def test_concurrent_batch_dispatch_all_members_marked_executing():
    """Every feature in the batch is marked 'executing' before return."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(5)]
    store = FakeStore(features)

    batch = concurrent_batch_dispatch(
        first_feature=features[0],
        max_concurrent_features=5,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    claimed = {fid for fid, status in store.update_calls if status == "executing"}
    batch_ids = {f.id for f in batch}
    assert batch_ids == claimed


def test_concurrent_batch_dispatch_no_duplicates():
    """Each feature appears at most once in the batch."""
    features = [FakeFeature(id=f"feat-{i}") for i in range(8)]
    store = FakeStore(features)

    batch = concurrent_batch_dispatch(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    ids = [f.id for f in batch]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# bob66 regression: 19 claimable features, 8-wide cap yields batch of 8
# ---------------------------------------------------------------------------


def test_concurrent_batch_dispatch_bob66_regression():
    """Regression: 19 claimable features with cap=8 yields batch of 8 (not 1)."""
    features = [FakeFeature(id=f"feat-{i:02d}") for i in range(19)]
    store = FakeStore(features)

    batch = concurrent_batch_dispatch(
        first_feature=features[0],
        max_concurrent_features=8,
        find_next_ready_feature=store.find_next_ready_feature,
        update_feature=store.update_feature,
    )

    assert len(batch) == 8, (
        f"Expected batch size 8 with 19 claimable features and cap=8, got {len(batch)}"
    )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_concurrent_batch_dispatch_none_first_feature_raises():
    """Passing None as first_feature raises ValueError."""
    with pytest.raises(ValueError, match="first_feature"):
        concurrent_batch_dispatch(
            first_feature=None,
            max_concurrent_features=2,
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )


def test_concurrent_batch_dispatch_non_integer_max_raises():
    """Passing a non-integer max_concurrent_features raises TypeError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        concurrent_batch_dispatch(
            first_feature=f1,
            max_concurrent_features="eight",  # type: ignore[arg-type]
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )


def test_concurrent_batch_dispatch_none_find_raises():
    """Passing None as find_next_ready_feature raises TypeError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        concurrent_batch_dispatch(
            first_feature=f1,
            max_concurrent_features=2,
            find_next_ready_feature=None,  # type: ignore[arg-type]
            update_feature=lambda fid, *, status: None,
        )


def test_concurrent_batch_dispatch_none_update_raises():
    """Passing None as update_feature raises TypeError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        concurrent_batch_dispatch(
            first_feature=f1,
            max_concurrent_features=2,
            find_next_ready_feature=lambda: None,
            update_feature=None,  # type: ignore[arg-type]
        )
