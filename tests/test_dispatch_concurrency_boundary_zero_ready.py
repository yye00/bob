"""Tests boundary case: dispatch_up_to_concurrency when zero ready features exist.

AC: pytest: tests/test_dispatch_concurrency_boundary_zero_ready.py
"""

from __future__ import annotations

import unittest.mock as mock

import pytest

from bob3.orchestrator.run_loop import dispatch_up_to_concurrency, current_concurrency_slots


def _make_loop_no_ready(cap: int):
    """Create a mock loop whose find_next_ready_feature always returns None."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-boundary"
    loop.find_next_ready_feature = mock.MagicMock(return_value=None)
    return loop


def test_dispatch_returns_empty_when_no_ready_features():
    """dispatch_up_to_concurrency returns [] when no ready features are available."""
    loop = _make_loop_no_ready(cap=3)

    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=set())

    assert claimed == []
    mock_db.update_feature.assert_not_called()


def test_dispatch_returns_empty_when_cap_fully_saturated():
    """dispatch_up_to_concurrency returns [] when active_feature_ids fills the cap."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 2
    loop.project_id = "proj-saturated"
    loop.find_next_ready_feature = mock.MagicMock()

    active = {"feat-a", "feat-b"}  # exactly at cap

    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=active)

    assert claimed == []
    # find_next_ready_feature should never be called when already saturated
    loop.find_next_ready_feature.assert_not_called()
    mock_db.update_feature.assert_not_called()


def test_dispatch_returns_empty_when_cap_exceeded():
    """dispatch_up_to_concurrency returns [] when active exceeds cap."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 2
    loop.project_id = "proj-over"
    loop.find_next_ready_feature = mock.MagicMock()

    active = {"feat-a", "feat-b", "feat-c"}  # over cap

    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=active)

    assert claimed == []
    loop.find_next_ready_feature.assert_not_called()


def test_current_concurrency_slots_zero_when_saturated():
    """current_concurrency_slots returns 0 when all slots are taken."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 3
    active = {"a", "b", "c"}

    assert current_concurrency_slots(loop, active_feature_ids=active) == 0


def test_current_concurrency_slots_zero_when_over_cap():
    """current_concurrency_slots returns 0 (not negative) when over cap."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 2
    active = {"a", "b", "c", "d"}

    result = current_concurrency_slots(loop, active_feature_ids=active)
    assert result == 0


def test_dispatch_with_cap_one_and_no_ready_returns_empty():
    """Works correctly in sequential mode (cap=1) with zero ready features."""
    loop = _make_loop_no_ready(cap=1)

    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=set())

    assert claimed == []
    mock_db.update_feature.assert_not_called()
