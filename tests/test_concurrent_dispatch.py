"""Tests for bob.orchestrator.concurrent_dispatch.

AC: pytest: tests/test_concurrent_dispatch.py

Verifies:
- dispatch_concurrent_features and gather_and_reap are importable
- dispatch_concurrent_features delegates to run_loop correctly
- gather_and_reap collects task outcomes with failure isolation
- gather_and_reap reaps (cancels) stuck tasks on timeout
- gather_and_reap raises ValueError for non-positive timeout
- Empty inputs return empty lists without raising
"""

from __future__ import annotations

import asyncio
import types
import unittest.mock as mock

import pytest

from bob.orchestrator.concurrent_dispatch import (
    dispatch_concurrent_features,
    gather_and_reap,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(fid: str) -> types.SimpleNamespace:
    f = types.SimpleNamespace()
    f.id = fid
    f.status = "ready"
    return f


def _make_loop(cap: int, ready_features: list) -> mock.MagicMock:
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-concurrent-dispatch-test"
    loop.find_next_ready_feature = mock.MagicMock(
        side_effect=list(ready_features) + [None]
    )
    return loop


# ---------------------------------------------------------------------------
# Module API surface
# ---------------------------------------------------------------------------

def test_dispatch_concurrent_features_is_importable():
    """dispatch_concurrent_features must be an importable async callable."""
    import inspect
    assert callable(dispatch_concurrent_features)
    assert inspect.iscoroutinefunction(dispatch_concurrent_features)


def test_gather_and_reap_is_importable():
    """gather_and_reap must be an importable async callable."""
    import inspect
    assert callable(gather_and_reap)
    assert inspect.iscoroutinefunction(gather_and_reap)


# ---------------------------------------------------------------------------
# dispatch_concurrent_features — basic behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_empty_ready_list_returns_empty():
    """No ready features → empty result list, no exception raised."""
    loop = _make_loop(cap=3, ready_features=[])

    async def noop(f):
        return "ok"

    with mock.patch("bob.orchestrator.run_loop.db"):
        result = await dispatch_concurrent_features(loop, worker=noop)

    assert result == []


@pytest.mark.asyncio
async def test_dispatch_single_feature_succeeds():
    """One ready feature is dispatched and its success recorded."""
    feature = _make_feature("feat-single")
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
    assert ran == ["feat-single"]


@pytest.mark.asyncio
async def test_dispatch_multiple_features_all_succeed():
    """Multiple ready features are all dispatched and collected."""
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    ran = []

    async def worker(f):
        ran.append(f.id)
        return "done"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=worker)

    assert len(result) == 3
    assert all(r["success"] for r in result)
    assert set(ran) == {"feat-0", "feat-1", "feat-2"}


@pytest.mark.asyncio
async def test_dispatch_failure_isolated_from_peers():
    """A failing worker does not prevent other features from completing."""
    features = [_make_feature("feat-ok"), _make_feature("feat-bad")]
    loop = _make_loop(cap=2, ready_features=features)

    async def worker(f):
        if f.id == "feat-bad":
            raise RuntimeError("intentional failure")
        return "done"

    with mock.patch("bob.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        result = await dispatch_concurrent_features(loop, worker=worker)

    assert len(result) == 2
    successes = {r["feature_id"]: r["success"] for r in result}
    assert successes["feat-ok"] is True
    assert successes["feat-bad"] is False


@pytest.mark.asyncio
async def test_dispatch_none_loop_raises_value_error():
    """Passing loop=None raises ValueError immediately."""
    async def noop(f):
        return "ok"

    with pytest.raises(ValueError, match="loop"):
        await dispatch_concurrent_features(None, worker=noop)


@pytest.mark.asyncio
async def test_dispatch_non_callable_worker_raises_value_error():
    """Passing a non-callable worker raises ValueError immediately."""
    loop = _make_loop(cap=3, ready_features=[])

    with pytest.raises(ValueError, match="worker"):
        await dispatch_concurrent_features(loop, worker="not_callable")


# ---------------------------------------------------------------------------
# gather_and_reap — basic collection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gather_and_reap_empty_list_returns_empty():
    """Empty task list returns [] without blocking."""
    result = await gather_and_reap([])
    assert result == []


@pytest.mark.asyncio
async def test_gather_and_reap_successful_task():
    """A successful task is recorded with success=True and correct result."""
    async def coro():
        return "value"

    task = asyncio.ensure_future(coro())
    results = await gather_and_reap([task])

    assert len(results) == 1
    assert results[0]["success"] is True
    assert results[0]["result"] == "value"
    assert results[0]["error"] is None


@pytest.mark.asyncio
async def test_gather_and_reap_failed_task():
    """A failing task is recorded with success=False and error set."""
    async def coro():
        raise ValueError("boom")

    task = asyncio.ensure_future(coro())
    results = await gather_and_reap([task])

    assert len(results) == 1
    assert results[0]["success"] is False
    assert results[0]["error"] is not None
    assert "boom" in results[0]["error"]


@pytest.mark.asyncio
async def test_gather_and_reap_mixed_tasks():
    """Mix of success and failure tasks are each reported independently."""
    async def ok():
        return "ok"

    async def bad():
        raise RuntimeError("fail")

    tasks = [asyncio.ensure_future(ok()), asyncio.ensure_future(bad())]
    results = await gather_and_reap(tasks)

    assert len(results) == 2
    successes = [r["success"] for r in results]
    assert True in successes
    assert False in successes


# ---------------------------------------------------------------------------
# gather_and_reap — timeout / reap behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gather_and_reap_timeout_reaps_stuck_task():
    """A task that exceeds the timeout is cancelled and recorded as error=timeout."""
    async def stuck():
        await asyncio.sleep(60)  # simulates a hung subagent

    task = asyncio.ensure_future(stuck())
    results = await gather_and_reap([task], timeout=0.05)

    assert len(results) == 1
    assert results[0]["success"] is False
    assert results[0]["error"] == "timeout"
    assert task.cancelled()


@pytest.mark.asyncio
async def test_gather_and_reap_timeout_does_not_reap_fast_task():
    """A task that completes before the timeout is not reaped."""
    async def fast():
        return "fast_result"

    task = asyncio.ensure_future(fast())
    results = await gather_and_reap([task], timeout=5.0)

    assert len(results) == 1
    assert results[0]["success"] is True
    assert results[0]["result"] == "fast_result"


@pytest.mark.asyncio
async def test_gather_and_reap_timeout_mixed_fast_and_stuck():
    """Fast task succeeds while stuck task is reaped — peers are not affected."""
    async def fast():
        return "fast"

    async def stuck():
        await asyncio.sleep(60)

    fast_task = asyncio.ensure_future(fast())
    stuck_task = asyncio.ensure_future(stuck())

    results = await gather_and_reap([fast_task, stuck_task], timeout=0.2)

    assert len(results) == 2
    result_by_task = {r["task"]: r for r in results}

    assert result_by_task[fast_task]["success"] is True
    assert result_by_task[fast_task]["result"] == "fast"

    assert result_by_task[stuck_task]["success"] is False
    assert result_by_task[stuck_task]["error"] == "timeout"


@pytest.mark.asyncio
async def test_gather_and_reap_non_positive_timeout_raises():
    """Timeout of zero or negative raises ValueError immediately."""
    async def coro():
        return "ok"

    task = asyncio.ensure_future(coro())
    with pytest.raises(ValueError):
        await gather_and_reap([task], timeout=0)
    # Clean up so no warning about task never awaited
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.asyncio
async def test_gather_and_reap_negative_timeout_raises():
    """Negative timeout raises ValueError."""
    async def coro():
        return "ok"

    task = asyncio.ensure_future(coro())
    with pytest.raises(ValueError):
        await gather_and_reap([task], timeout=-1.0)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
