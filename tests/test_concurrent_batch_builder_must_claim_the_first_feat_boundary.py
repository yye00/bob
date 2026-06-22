"""Boundary-case tests for claim_first_feature_before_batch_building.

Feature 9d2d1835-fac6-4ebd-a3d2-7a26216fbb5b

Verifies that empty, zero, or minimum inputs return a well-defined result
rather than raising an exception.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from bob3.run_loop import claim_first_feature_before_batch_building


@dataclass
class FakeFeature:
    id: str
    status: str = "ready"


# ---------------------------------------------------------------------------
# Boundary: max_concurrent_features == 0 or negative
# ---------------------------------------------------------------------------


def test_max_concurrent_0_returns_single_feature():
    """max_concurrent_features=0 is treated as sequential (cap to 1), returns [first_feature]."""
    f1 = FakeFeature(id="feat-1")
    updates: list = []

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=0,
        find_next_ready_feature=lambda: None,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    assert len(batch) == 1
    assert batch[0].id == "feat-1"
    # No claims in sequential path
    assert updates == []


def test_max_concurrent_negative_returns_single_feature():
    """Negative max_concurrent_features is treated as sequential, returns [first_feature]."""
    f1 = FakeFeature(id="feat-1")
    updates: list = []

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=-5,
        find_next_ready_feature=lambda: None,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    assert len(batch) == 1
    assert batch[0].id == "feat-1"


# ---------------------------------------------------------------------------
# Boundary: find_next_ready_feature always returns None (no additional features)
# ---------------------------------------------------------------------------


def test_find_always_none_returns_size_1_batch():
    """When find_next_ready_feature always returns None, batch stays size 1."""
    f1 = FakeFeature(id="feat-only")
    updates: list = []

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=8,
        find_next_ready_feature=lambda: None,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    assert len(batch) == 1
    assert batch[0].id == "feat-only"


# ---------------------------------------------------------------------------
# Boundary: exactly 1 additional feature claimable (cap = 2)
# ---------------------------------------------------------------------------


def test_exactly_one_additional_feature_at_cap_2():
    """With cap=2 and exactly 2 features, batch size == 2 (minimum multi-feature batch)."""
    f1 = FakeFeature(id="feat-1")
    f2 = FakeFeature(id="feat-2")
    claimed: dict[str, str] = {}

    def update(fid: str, *, status: str) -> None:
        claimed[fid] = status
        if fid == "feat-1":
            f1.status = status
        elif fid == "feat-2":
            f2.status = status

    def find_next() -> FakeFeature | None:
        if f2.status == "ready":
            return f2
        return None

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=2,
        find_next_ready_feature=find_next,
        update_feature=update,
    )

    assert len(batch) == 2
    assert batch[0].id == "feat-1"
    assert batch[1].id == "feat-2"


# ---------------------------------------------------------------------------
# Boundary: first feature returned by find (dedup guard catches it)
# ---------------------------------------------------------------------------


def test_dedup_guard_prevents_duplicate_first_feature():
    """When find_next_ready_feature returns first_feature again (pre-claim missed),
    the dedup guard prevents it from being added twice. With the fix applied,
    this should not happen, but the guard is still a safety net."""
    f1 = FakeFeature(id="feat-1")

    # Simulate a broken store that always returns f1 despite claiming
    # (tests that the dedup guard also works as a backstop)
    call_count = [0]

    def buggy_find() -> FakeFeature | None:
        call_count[0] += 1
        if call_count[0] > 3:
            return None
        return f1  # always returns the same feature

    updates: list = []

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=4,
        find_next_ready_feature=buggy_find,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    # dedup guard prevents first_feature from appearing more than once
    ids = [f.id for f in batch]
    assert ids.count("feat-1") == 1
    assert len(batch) == 1


# ---------------------------------------------------------------------------
# Boundary: max_concurrent_features == 1 means no claiming at all
# ---------------------------------------------------------------------------


def test_sequential_path_no_side_effects():
    """max_concurrent_features=1 → no update calls, no find calls."""
    f1 = FakeFeature(id="feat-1")
    find_calls = [0]
    updates: list = []

    def counting_find() -> FakeFeature | None:
        find_calls[0] += 1
        return None

    batch = claim_first_feature_before_batch_building(
        first_feature=f1,
        max_concurrent_features=1,
        find_next_ready_feature=counting_find,
        update_feature=lambda fid, *, status: updates.append((fid, status)),
    )

    assert len(batch) == 1
    assert find_calls[0] == 0
    assert updates == []


# ---------------------------------------------------------------------------
# Boundary: batch size == max_concurrent_features exactly (saturated)
# ---------------------------------------------------------------------------


def test_saturated_batch_equals_cap_exactly():
    """When exactly max_concurrent_features features exist, batch fills to cap."""
    cap = 5
    features = [FakeFeature(id=f"feat-{i}") for i in range(cap)]
    status_map: dict[str, str] = {f.id: "ready" for f in features}

    def update(fid: str, *, status: str) -> None:
        status_map[fid] = status

    def find_next() -> FakeFeature | None:
        for feat in features:
            if status_map[feat.id] == "ready":
                return feat
        return None

    batch = claim_first_feature_before_batch_building(
        first_feature=features[0],
        max_concurrent_features=cap,
        find_next_ready_feature=find_next,
        update_feature=update,
    )

    assert len(batch) == cap
