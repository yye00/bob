"""Tests that dispatch_up_to_concurrency fills slots up to the cap.

AC: pytest: tests/test_dispatch_concurrency_fills_to_cap.py
"""

from __future__ import annotations

import types
import unittest.mock as mock

import pytest

from bob.orchestrator.run_loop import dispatch_up_to_concurrency, current_concurrency_slots


def _make_feature(feature_id: str, status: str = "ready"):
    f = types.SimpleNamespace()
    f.id = feature_id
    f.status = status
    return f


def _make_loop(cap: int, ready_features: list):
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-test"
    loop.find_next_ready_feature = mock.MagicMock(side_effect=list(ready_features) + [None])
    return loop


def test_fills_all_slots_when_enough_ready(monkeypatch):
    """dispatch_up_to_concurrency claims up to cap features when all are available."""
    cap = 3
    features = [_make_feature(f"feat-{i}") for i in range(5)]
    loop = _make_loop(cap, features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=set())

    assert len(claimed) == cap
    assert {f.id for f in claimed} == {"feat-0", "feat-1", "feat-2"}
    # Each claimed feature should have been marked executing
    assert mock_db.update_feature.call_count == cap


def test_fills_remaining_slots_when_some_active(monkeypatch):
    """dispatch_up_to_concurrency fills only the open slots when some are already active."""
    cap = 3
    already_active = {"feat-already"}
    features = [_make_feature(f"feat-new-{i}") for i in range(3)]
    loop = _make_loop(cap, features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=already_active)

    # 3 cap - 1 already active = 2 open slots
    assert len(claimed) == 2
    assert mock_db.update_feature.call_count == 2


def test_does_not_exceed_cap_even_with_many_ready():
    """dispatch_up_to_concurrency never returns more than cap features."""
    cap = 2
    features = [_make_feature(f"feat-{i}") for i in range(10)]
    loop = _make_loop(cap, features)

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=set())

    assert len(claimed) <= cap
    assert len(claimed) == 2


def test_current_concurrency_slots_returns_cap_minus_active():
    """current_concurrency_slots returns cap minus the count of active features."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 4

    assert current_concurrency_slots(loop, active_feature_ids=set()) == 4
    assert current_concurrency_slots(loop, active_feature_ids={"a", "b"}) == 2
    assert current_concurrency_slots(loop, active_feature_ids={"a", "b", "c", "d"}) == 0
    assert current_concurrency_slots(loop, active_feature_ids={"a", "b", "c", "d", "e"}) == 0


def test_current_concurrency_slots_no_active_returns_cap():
    """current_concurrency_slots returns cap directly when active_feature_ids is None."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 5

    result = current_concurrency_slots(loop, active_feature_ids=None)
    assert result == 5
