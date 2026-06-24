"""Tests for orchestrator dispatch concurrency (feature 26a9ae10).

Verifies that dispatch_concurrent_features:
- Is importable from bob.orchestrator
- Returns empty list when no slots are available
- Dispatches all claimed features concurrently
- Isolates worker failures (one hung/failing worker does not block peers)
- Respects BOB_MAX_CONCURRENT_FEATURES env override
- Invokes on_failure callback on worker error

AC: pytest: tests/test_orchestrator_concurrency.py
AC: integration: bob.orchestrator
"""

from __future__ import annotations

import asyncio
import types
import unittest.mock as mock

import pytest

from bob.orchestrator import dispatch_concurrent_features
from bob.orchestrator.run_loop import (
    _resolve_max_concurrent_features,
    dispatch_up_to_concurrency,
    current_concurrency_slots,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(feature_id: str, status: str = "ready"):
    f = types.SimpleNamespace()
    f.id = feature_id
    f.status = status
    return f


def _make_loop(cap: int, ready_features: list):
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-concurrency-test"
    loop.find_next_ready_feature = mock.MagicMock(side_effect=list(ready_features) + [None])
    return loop


# ---------------------------------------------------------------------------
# Integration AC: dispatch_concurrent_features importable from bob.orchestrator
# ---------------------------------------------------------------------------

def test_dispatch_concurrent_features_importable_from_bob_orchestrator():
    """dispatch_concurrent_features must be importable from bob.orchestrator."""
    from bob.orchestrator import dispatch_concurrent_features as dcf
    assert callable(dcf)


def test_dispatch_concurrent_features_is_coroutine_function():
    """dispatch_concurrent_features must be an async function."""
    import inspect
    assert inspect.iscoroutinefunction(dispatch_concurrent_features)


# ---------------------------------------------------------------------------
# Empty / no-slots edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_concurrent_features_empty_when_no_ready_features():
    """Returns empty list when no ready features are available."""
    loop = _make_loop(cap=3, ready_features=[])

    async def noop_worker(feature):
        return "done"

    with mock.patch("bob.orchestrator.run_loop.db"):
        results = await dispatch_concurrent_features(loop, worker=noop_worker)

    assert results == []


@pytest.mark.asyncio
async def test_dispatch_concurrent_features_empty_when_cap_saturated():
    """Returns empty list when all concurrency slots are already in use."""
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    active = {"feat-0", "feat-1", "feat-2"}

    async def noop_worker(feature):
        return "done"

    with mock.patch("bob.orchestrator.run_loop.db"):
        results = await dispatch_concurrent_features(
            loop,
            worker=noop_worker,
            active_feature_ids=active,
        )

    assert results == []


# ---------------------------------------------------------------------------
# Successful concurrent dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_concurrent_features_dispatches_all_claimed():
    """dispatch_concurrent_features runs worker for each claimed feature."""
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    dispatched_ids: list[str] = []

    async def tracking_worker(feature):
        dispatched_ids.append(feature.id)
        return f"result-{feature.id}"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        results = await dispatch_concurrent_features(
            loop,
            worker=tracking_worker,
            active_feature_ids=set(),
        )

    assert len(results) == 3
    assert all(r["success"] for r in results)
    assert set(dispatched_ids) == {"feat-0", "feat-1", "feat-2"}


@pytest.mark.asyncio
async def test_dispatch_concurrent_features_result_structure():
    """Each result dict has feature_id, success, result, and error fields."""
    feature = _make_feature("feat-abc")
    loop = _make_loop(cap=1, ready_features=[feature])

    async def simple_worker(f):
        return "output"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        results = await dispatch_concurrent_features(loop, worker=simple_worker)

    assert len(results) == 1
    r = results[0]
    assert r["feature_id"] == "feat-abc"
    assert r["success"] is True
    assert r["result"] == "output"
    assert r["error"] is None


# ---------------------------------------------------------------------------
# Failure isolation: one failing worker must not block peers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_concurrent_features_failure_isolation():
    """A failing worker does not prevent peer workers from completing."""
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    completed: list[str] = []

    async def worker(feature):
        if feature.id == "feat-1":
            raise RuntimeError("intentional failure in feat-1")
        await asyncio.sleep(0)
        completed.append(feature.id)
        return f"ok-{feature.id}"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        results = await dispatch_concurrent_features(
            loop,
            worker=worker,
            active_feature_ids=set(),
        )

    assert len(results) == 3
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    assert len(successes) == 2
    assert len(failures) == 1
    assert "intentional failure in feat-1" in failures[0]["error"]
    # Peers completed despite the failure
    assert set(completed) == {"feat-0", "feat-2"}


@pytest.mark.asyncio
async def test_dispatch_concurrent_features_on_failure_callback_invoked():
    """on_failure callback is invoked when a worker raises."""
    feature = _make_feature("feat-bad")
    loop = _make_loop(cap=1, ready_features=[feature])
    failure_log: list[tuple] = []

    async def bad_worker(f):
        raise ValueError("bang")

    def on_failure(f, exc):
        failure_log.append((f.id, str(exc)))

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        results = await dispatch_concurrent_features(
            loop,
            worker=bad_worker,
            on_failure=on_failure,
        )

    assert len(results) == 1
    assert not results[0]["success"]
    assert len(failure_log) == 1
    assert failure_log[0] == ("feat-bad", "bang")


@pytest.mark.asyncio
async def test_dispatch_concurrent_features_on_failure_callback_exception_swallowed():
    """Exceptions raised inside on_failure do not propagate to the caller."""
    feature = _make_feature("feat-bad")
    loop = _make_loop(cap=1, ready_features=[feature])

    async def bad_worker(f):
        raise ValueError("worker error")

    def exploding_callback(f, exc):
        raise RuntimeError("callback exploded")

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        # Must not raise even though the callback raises
        results = await dispatch_concurrent_features(
            loop,
            worker=bad_worker,
            on_failure=exploding_callback,
        )

    assert len(results) == 1
    assert not results[0]["success"]


# ---------------------------------------------------------------------------
# BOB_MAX_CONCURRENT_FEATURES env variable
# ---------------------------------------------------------------------------

def test_resolve_max_concurrent_features_default_is_three(monkeypatch):
    """Default concurrency cap is 3 when env var is unset."""
    monkeypatch.delenv("BOB_MAX_CONCURRENT_FEATURES", raising=False)
    assert _resolve_max_concurrent_features() == 3


def test_resolve_max_concurrent_features_env_override(monkeypatch):
    """BOB_MAX_CONCURRENT_FEATURES env var overrides the default."""
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "5")
    assert _resolve_max_concurrent_features() == 5


def test_resolve_max_concurrent_features_clamps_non_positive(monkeypatch):
    """Non-positive BOB_MAX_CONCURRENT_FEATURES is clamped to 1."""
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "0")
    assert _resolve_max_concurrent_features() == 1

    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "-5")
    assert _resolve_max_concurrent_features() == 1


def test_resolve_max_concurrent_features_invalid_falls_back(monkeypatch):
    """Invalid (non-integer) env var falls back to default (3)."""
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "not-a-number")
    assert _resolve_max_concurrent_features() == 3


# ---------------------------------------------------------------------------
# Concurrency: verify actual parallel execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_concurrent_features_runs_workers_concurrently():
    """Multiple workers execute concurrently (not sequentially one by one)."""
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    start_times: dict[str, float] = {}
    end_times: dict[str, float] = {}

    async def timed_worker(feature):
        start_times[feature.id] = asyncio.get_event_loop().time()
        await asyncio.sleep(0.05)
        end_times[feature.id] = asyncio.get_event_loop().time()
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db, \
         mock.patch.dict("os.environ", {"BOB_MAX_CONCURRENT_FEATURES": "3"}):
        mock_db.update_feature = mock.MagicMock()
        results = await dispatch_concurrent_features(
            loop,
            worker=timed_worker,
            active_feature_ids=set(),
        )

    assert len(results) == 3
    # If concurrent, all start before any end: max(start) < min(end)
    assert max(start_times.values()) < min(end_times.values()) + 0.02


# ---------------------------------------------------------------------------
# current_concurrency_slots helper
# ---------------------------------------------------------------------------

def test_current_concurrency_slots_zero_when_saturated():
    """Returns 0 when all cap slots are occupied."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 3
    active = {"a", "b", "c"}
    assert current_concurrency_slots(loop, active_feature_ids=active) == 0


def test_current_concurrency_slots_never_negative():
    """Never returns a negative value even if active > cap."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 2
    active = {"a", "b", "c", "d"}
    assert current_concurrency_slots(loop, active_feature_ids=active) == 0
