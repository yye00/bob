"""Tests for bob.concurrent_dispatcher.

Verifies the module-level dispatch_concurrent_features and
gather_completed_features functions behave correctly, including
concurrent dispatch, failure isolation, and the gather pathway.

AC: pytest: tests/test_concurrent_dispatcher.py
"""

from __future__ import annotations

import asyncio
import types
import unittest.mock as mock

import pytest

from bob.concurrent_dispatcher import (
    dispatch_concurrent_features,
    gather_completed_features,
)


def _make_loop(cap: int, ready_features: list):
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-test"
    loop.find_next_ready_feature = mock.MagicMock(
        side_effect=list(ready_features) + [None]
    )
    return loop


def _make_feature(fid: str):
    f = types.SimpleNamespace()
    f.id = fid
    f.status = "ready"
    return f


# ---------------------------------------------------------------------------
# Module-level API surface checks
# ---------------------------------------------------------------------------

def test_dispatch_concurrent_features_is_callable():
    """dispatch_concurrent_features must be an importable async callable."""
    import inspect
    assert callable(dispatch_concurrent_features)
    assert inspect.iscoroutinefunction(dispatch_concurrent_features)


def test_gather_completed_features_is_callable():
    """gather_completed_features must be an importable async callable."""
    import inspect
    assert callable(gather_completed_features)
    assert inspect.iscoroutinefunction(gather_completed_features)


# ---------------------------------------------------------------------------
# dispatch_concurrent_features — basic dispatch behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_empty_queue_returns_empty():
    """No ready features → empty result list, no exception."""
    loop = _make_loop(cap=3, ready_features=[])

    async def noop(f):
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db"):
        result = await dispatch_concurrent_features(loop, worker=noop)

    assert result == []


@pytest.mark.asyncio
async def test_dispatch_single_feature_succeeds():
    """One ready feature is dispatched and its success is recorded."""
    feature = _make_feature("feat-1")
    loop = _make_loop(cap=3, ready_features=[feature])
    ran = []

    async def worker(f):
        ran.append(f.id)
        return "done"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=worker)

    assert len(result) == 1
    assert result[0]["success"] is True
    assert ran == ["feat-1"]


@pytest.mark.asyncio
async def test_dispatch_multiple_features_all_succeed():
    """Multiple ready features are all dispatched and collected."""
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    ran = []

    async def worker(f):
        ran.append(f.id)
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=worker)

    assert len(result) == 3
    assert all(r["success"] for r in result)
    assert set(ran) == {"feat-0", "feat-1", "feat-2"}


@pytest.mark.asyncio
async def test_dispatch_worker_failure_isolated():
    """A failing worker is captured as success=False; other slots still ok."""
    feature = _make_feature("feat-bad")
    loop = _make_loop(cap=1, ready_features=[feature])

    async def bad_worker(f):
        raise RuntimeError("worker exploded")

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=bad_worker)

    assert len(result) == 1
    assert result[0]["success"] is False
    assert "worker exploded" in result[0]["error"]


@pytest.mark.asyncio
async def test_dispatch_on_failure_callback_called():
    """on_failure callback is invoked when a worker raises."""
    feature = _make_feature("feat-cb")
    loop = _make_loop(cap=1, ready_features=[feature])
    failures = []

    def on_fail(f, exc):
        failures.append((f.id, str(exc)))

    async def bad_worker(f):
        raise ValueError("boom")

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        await dispatch_concurrent_features(loop, worker=bad_worker, on_failure=on_fail)

    assert len(failures) == 1
    assert failures[0][0] == "feat-cb"
    assert "boom" in failures[0][1]


@pytest.mark.asyncio
async def test_dispatch_respects_active_feature_ids():
    """Features already in active_feature_ids are not double-dispatched."""
    feature = _make_feature("feat-already")
    loop = _make_loop(cap=3, ready_features=[feature])
    # Report the feature as already in-flight; cap is 3 but 1 slot used
    # and find_next_ready_feature returns the same feature → skip it
    loop.find_next_ready_feature = mock.MagicMock(return_value=feature)

    async def noop(f):
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db"):
        result = await dispatch_concurrent_features(
            loop, worker=noop, active_feature_ids={"feat-already"}
        )

    # The feature is in-flight and would be returned by find_next_ready_feature,
    # but the dispatcher must skip it.
    assert result == []


@pytest.mark.asyncio
async def test_dispatch_none_loop_raises_value_error():
    """loop=None raises ValueError without silently succeeding."""
    async def noop(f):
        return "ok"

    with pytest.raises(ValueError, match="loop"):
        await dispatch_concurrent_features(None, worker=noop)


@pytest.mark.asyncio
async def test_dispatch_non_callable_worker_raises_value_error():
    """A non-callable worker raises ValueError immediately."""
    loop = _make_loop(cap=3, ready_features=[])
    with pytest.raises(ValueError, match="worker"):
        await dispatch_concurrent_features(loop, worker="not_callable")


# ---------------------------------------------------------------------------
# gather_completed_features
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gather_empty_list_returns_empty():
    """Passing an empty task list returns [] without blocking."""
    result = await gather_completed_features([])
    assert result == []


@pytest.mark.asyncio
async def test_gather_single_successful_task():
    """A single completed task returns success=True with its result."""
    async def coro():
        return 42

    task = asyncio.ensure_future(coro())
    await asyncio.sleep(0)  # allow task to complete

    result = await gather_completed_features([task])
    assert len(result) == 1
    assert result[0]["success"] is True
    assert result[0]["result"] == 42
    assert result[0]["error"] is None


@pytest.mark.asyncio
async def test_gather_failing_task_captured_as_failure():
    """A task that raises an exception is captured with success=False."""
    async def coro():
        raise RuntimeError("task failed")

    task = asyncio.ensure_future(coro())
    await asyncio.sleep(0)

    result = await gather_completed_features([task])
    assert len(result) == 1
    assert result[0]["success"] is False
    assert "task failed" in result[0]["error"]


@pytest.mark.asyncio
async def test_gather_mixed_success_and_failure():
    """Mixed outcomes are all collected; failures don't cancel siblings."""
    async def ok():
        return "good"

    async def bad():
        raise ValueError("bad")

    t1 = asyncio.ensure_future(ok())
    t2 = asyncio.ensure_future(bad())
    await asyncio.sleep(0)

    result = await gather_completed_features([t1, t2])
    assert len(result) == 2
    successes = [r for r in result if r["success"]]
    failures = [r for r in result if not r["success"]]
    assert len(successes) == 1
    assert len(failures) == 1
    assert successes[0]["result"] == "good"
    assert "bad" in failures[0]["error"]


@pytest.mark.asyncio
async def test_gather_preserves_task_reference():
    """Each result dict includes the original task object."""
    async def coro():
        return "x"

    task = asyncio.ensure_future(coro())
    result = await gather_completed_features([task])
    assert result[0]["task"] is task
