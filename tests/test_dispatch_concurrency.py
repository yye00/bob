"""Tests for :mod:`bob.dispatch_concurrency`.

Feature 16743e36: orchestrator dispatch concurrency — public seam exposing
``max_concurrent_features`` and ``fill_ready_slots``.
"""

from __future__ import annotations

import types
import unittest.mock as mock

import pytest

from bob import dispatch_concurrency


def _make_feature(fid: str):
    f = types.SimpleNamespace()
    f.id = fid
    f.status = "ready"
    return f


def _make_loop(cap: int, ready_features: list):
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-test"
    loop.find_next_ready_feature = mock.MagicMock(
        side_effect=list(ready_features) + [None]
    )
    return loop


# ---------------------------------------------------------------------------
# max_concurrent_features
# ---------------------------------------------------------------------------

def test_max_concurrent_features_default_is_three(monkeypatch):
    monkeypatch.delenv("BOB_MAX_CONCURRENT_FEATURES", raising=False)
    assert dispatch_concurrency.max_concurrent_features() == 3


def test_max_concurrent_features_honors_env(monkeypatch):
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "7")
    assert dispatch_concurrency.max_concurrent_features() == 7


def test_max_concurrent_features_clamps_nonpositive(monkeypatch):
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "0")
    assert dispatch_concurrency.max_concurrent_features() == 1


def test_max_concurrent_features_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "not-a-number")
    assert dispatch_concurrency.max_concurrent_features() == 3


def test_max_concurrent_features_always_at_least_one(monkeypatch):
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "-5")
    assert dispatch_concurrency.max_concurrent_features() >= 1


# ---------------------------------------------------------------------------
# fill_ready_slots
# ---------------------------------------------------------------------------

def test_fill_ready_slots_claims_up_to_cap():
    features = [_make_feature(f"feat-{i}") for i in range(5)]
    loop = _make_loop(cap=3, ready_features=features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_concurrency.fill_ready_slots(loop)

    assert [f.id for f in claimed] == ["feat-0", "feat-1", "feat-2"]
    # Each claimed feature is marked executing.
    assert mock_db.update_feature.call_count == 3


def test_fill_ready_slots_respects_in_flight():
    features = [_make_feature("feat-a"), _make_feature("feat-b")]
    loop = _make_loop(cap=3, ready_features=features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        # Two already in flight → only one slot open.
        claimed = dispatch_concurrency.fill_ready_slots(
            loop, active_feature_ids={"x", "y"}
        )

    assert len(claimed) == 1
    assert claimed[0].id == "feat-a"


def test_fill_ready_slots_empty_when_no_ready_features():
    loop = _make_loop(cap=3, ready_features=[])

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_concurrency.fill_ready_slots(loop)

    assert claimed == []


def test_fill_ready_slots_empty_when_cap_saturated():
    features = [_make_feature("feat-a")]
    loop = _make_loop(cap=2, ready_features=features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_concurrency.fill_ready_slots(
            loop, active_feature_ids={"in1", "in2"}
        )

    assert claimed == []


def test_fill_ready_slots_none_loop_raises_value_error():
    with pytest.raises(ValueError, match="loop"):
        dispatch_concurrency.fill_ready_slots(None)


def test_fill_ready_slots_skips_already_active_features():
    features = [_make_feature("feat-dup"), _make_feature("feat-new")]
    loop = _make_loop(cap=3, ready_features=features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        # feat-dup is already in flight; loop must stop when it re-surfaces it.
        claimed = dispatch_concurrency.fill_ready_slots(
            loop, active_feature_ids={"feat-dup"}
        )

    # find_next_ready_feature returns feat-dup first which is already active,
    # so the claim loop breaks — no features claimed this tick.
    assert all(f.id != "feat-dup" for f in claimed)
