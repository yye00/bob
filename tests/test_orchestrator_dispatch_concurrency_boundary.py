"""Boundary-case tests for orchestrator dispatch concurrency.

AC: pytest: tests/test_orchestrator_dispatch_concurrency_boundary.py — empty,
    zero, or minimum input returns a well-defined result rather than raising
    (boundary case).
"""

from __future__ import annotations

import types
import unittest.mock as mock

import pytest

from bob.orchestrator.run_loop import (
    dispatch_concurrent_features,
    current_concurrency_slots,
    _resolve_max_concurrent_features,
)


def _make_loop(cap: int, ready_features: list):
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-boundary-test"
    loop.find_next_ready_feature = mock.MagicMock(side_effect=list(ready_features) + [None])
    return loop


def _make_feature(fid: str):
    f = types.SimpleNamespace()
    f.id = fid
    f.status = "ready"
    return f


# ---------------------------------------------------------------------------
# Empty / zero-features boundary cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_empty_ready_list_returns_empty_list():
    """Empty ready queue returns empty list without raising."""
    loop = _make_loop(cap=3, ready_features=[])

    async def noop(feature):
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db"):
        result = await dispatch_concurrent_features(loop, worker=noop)

    assert result == []


@pytest.mark.asyncio
async def test_dispatch_cap_of_one_with_one_feature():
    """Minimum cap (1) with one feature dispatches exactly one feature."""
    feature = _make_feature("feat-min")
    loop = _make_loop(cap=1, ready_features=[feature])
    dispatched = []

    async def tracking(f):
        dispatched.append(f.id)
        return "done"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=tracking)

    assert len(result) == 1
    assert result[0]["success"] is True
    assert dispatched == ["feat-min"]


@pytest.mark.asyncio
async def test_dispatch_active_ids_none_treated_as_empty():
    """Passing active_feature_ids=None does not raise; treated as no in-flight."""
    feature = _make_feature("feat-x")
    loop = _make_loop(cap=1, ready_features=[feature])

    async def noop(f):
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(
            loop, worker=noop, active_feature_ids=None
        )

    assert len(result) == 1
    assert result[0]["success"] is True


@pytest.mark.asyncio
async def test_dispatch_active_ids_empty_set_treated_as_no_in_flight():
    """Passing active_feature_ids=set() does not raise; all slots are open."""
    feature = _make_feature("feat-y")
    loop = _make_loop(cap=2, ready_features=[feature])

    async def noop(f):
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(
            loop, worker=noop, active_feature_ids=set()
        )

    assert len(result) == 1
    assert result[0]["success"] is True


# ---------------------------------------------------------------------------
# current_concurrency_slots boundary cases
# ---------------------------------------------------------------------------

def test_current_concurrency_slots_cap_zero_returns_zero():
    """Cap of zero means no slots open (clamped)."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 0
    slots = current_concurrency_slots(loop, active_feature_ids=set())
    assert slots == 0


def test_current_concurrency_slots_active_none_returns_cap():
    """When active_feature_ids is None, all cap slots are open."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 5
    slots = current_concurrency_slots(loop, active_feature_ids=None)
    assert slots == 5


def test_current_concurrency_slots_exact_fill_returns_zero():
    """When active count equals cap exactly, zero slots remain."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 2
    active = {"a", "b"}
    assert current_concurrency_slots(loop, active_feature_ids=active) == 0


# ---------------------------------------------------------------------------
# _resolve_max_concurrent_features boundary cases
# ---------------------------------------------------------------------------

def test_resolve_max_concurrent_features_env_one(monkeypatch):
    """Minimum valid setting (1) is accepted and returned."""
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "1")
    assert _resolve_max_concurrent_features() == 1


@pytest.mark.asyncio
async def test_dispatch_on_failure_none_does_not_raise():
    """on_failure=None (default) does not cause any error on worker failure."""
    feature = _make_feature("feat-bad")
    loop = _make_loop(cap=1, ready_features=[feature])

    async def bad_worker(f):
        raise RuntimeError("oops")

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=bad_worker, on_failure=None)

    assert len(result) == 1
    assert result[0]["success"] is False
    assert "oops" in result[0]["error"]
