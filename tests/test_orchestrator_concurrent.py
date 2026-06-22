"""Tests for bob3.orchestrator_concurrent — ConcurrentDispatchSlot and dispatch_concurrent_features.

AC: File exists: src/bob3/orchestrator_concurrent.py
AC: Function defined: bob3.orchestrator.dispatch_concurrent_features
AC: Function defined: bob3.orchestrator.ConcurrentDispatchSlot
AC: pytest: tests/test_orchestrator_concurrent.py
AC: integration: bob3.orchestrator
"""

from __future__ import annotations

import asyncio
import types
import unittest.mock as mock

import pytest

from bob3.orchestrator_concurrent import ConcurrentDispatchSlot


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
    loop.project_id = "proj-concurrent-test"
    loop.find_next_ready_feature = mock.MagicMock(
        side_effect=list(ready_features) + [None]
    )
    return loop


async def _done_task(result=None):
    return result


async def _failing_task():
    raise RuntimeError("simulated failure")


# ---------------------------------------------------------------------------
# Import / structural tests
# ---------------------------------------------------------------------------

def test_concurrent_dispatch_slot_importable():
    """ConcurrentDispatchSlot is importable from bob3.orchestrator_concurrent."""
    assert ConcurrentDispatchSlot is not None
    assert callable(ConcurrentDispatchSlot)


def test_dispatch_concurrent_features_importable_from_orchestrator_concurrent():
    """dispatch_concurrent_features is accessible from bob3.orchestrator_concurrent."""
    from bob3.orchestrator_concurrent import dispatch_concurrent_features
    assert callable(dispatch_concurrent_features)


def test_dispatch_concurrent_features_importable_from_orchestrator():
    """dispatch_concurrent_features is importable from bob3.orchestrator (integration AC)."""
    from bob3.orchestrator import dispatch_concurrent_features
    assert callable(dispatch_concurrent_features)


def test_concurrent_dispatch_slot_importable_from_orchestrator():
    """ConcurrentDispatchSlot is importable from bob3.orchestrator (integration AC)."""
    from bob3.orchestrator import ConcurrentDispatchSlot as CDS
    assert CDS is ConcurrentDispatchSlot


# ---------------------------------------------------------------------------
# ConcurrentDispatchSlot — construction and validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slot_construction_success():
    """ConcurrentDispatchSlot accepts a feature and a running asyncio.Task."""
    feature = _make_feature("feat-1")
    task = asyncio.create_task(_done_task("ok"))
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    assert slot.feature is feature
    assert slot.feature_id == "feat-1"
    assert slot.task is task
    assert slot.done is False
    assert slot.result is None
    assert slot.error is None
    await task


@pytest.mark.asyncio
async def test_slot_none_feature_raises_value_error():
    """Passing feature=None to ConcurrentDispatchSlot raises ValueError."""
    task = asyncio.create_task(_done_task())
    with pytest.raises(ValueError, match="feature"):
        ConcurrentDispatchSlot(feature=None, task=task)
    await task


@pytest.mark.asyncio
async def test_slot_non_task_raises_value_error():
    """Passing a non-Task as task raises ValueError."""
    feature = _make_feature("feat-x")
    with pytest.raises(ValueError, match="task"):
        ConcurrentDispatchSlot(feature=feature, task="not-a-task")


# ---------------------------------------------------------------------------
# ConcurrentDispatchSlot — is_done
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slot_is_done_false_while_running():
    """is_done() returns False while the task has not yet completed."""
    feature = _make_feature("feat-running")
    event = asyncio.Event()

    async def waiter():
        await event.wait()

    task = asyncio.create_task(waiter())
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    assert slot.is_done() is False
    event.set()
    await task
    assert slot.is_done() is True


@pytest.mark.asyncio
async def test_slot_is_done_true_after_completion():
    """is_done() returns True once the task has finished."""
    feature = _make_feature("feat-done")
    task = asyncio.create_task(_done_task("result"))
    await task
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    assert slot.is_done() is True


# ---------------------------------------------------------------------------
# ConcurrentDispatchSlot — collect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slot_collect_success():
    """collect() returns a success dict with result after task completes normally."""
    feature = _make_feature("feat-success")
    task = asyncio.create_task(_done_task("my-result"))
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    await task
    outcome = slot.collect()
    assert outcome["feature_id"] == "feat-success"
    assert outcome["success"] is True
    assert outcome["result"] == "my-result"
    assert outcome["error"] is None


@pytest.mark.asyncio
async def test_slot_collect_failure():
    """collect() returns a failure dict with error string when task raises."""
    feature = _make_feature("feat-fail")
    task = asyncio.create_task(_failing_task())
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    with pytest.raises(RuntimeError):
        await task
    outcome = slot.collect()
    assert outcome["feature_id"] == "feat-fail"
    assert outcome["success"] is False
    assert outcome["result"] is None
    assert "simulated failure" in outcome["error"]


@pytest.mark.asyncio
async def test_slot_collect_before_done_raises_runtime_error():
    """collect() raises RuntimeError if the task has not yet completed."""
    feature = _make_feature("feat-pending")
    event = asyncio.Event()

    async def waiter():
        await event.wait()

    task = asyncio.create_task(waiter())
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    with pytest.raises(RuntimeError, match="still running"):
        slot.collect()
    event.set()
    await task


@pytest.mark.asyncio
async def test_slot_collect_idempotent():
    """Calling collect() multiple times returns the same cached result."""
    feature = _make_feature("feat-idem")
    task = asyncio.create_task(_done_task(42))
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    await task
    first = slot.collect()
    second = slot.collect()
    assert first == second
    assert first["result"] == 42


# ---------------------------------------------------------------------------
# ConcurrentDispatchSlot — repr
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slot_repr_contains_feature_id():
    """repr(slot) contains the feature_id for debugging."""
    feature = _make_feature("feat-repr")
    task = asyncio.create_task(_done_task())
    slot = ConcurrentDispatchSlot(feature=feature, task=task)
    r = repr(slot)
    assert "feat-repr" in r
    await task


# ---------------------------------------------------------------------------
# ConcurrentDispatchSlot — feature_id fallback
# ---------------------------------------------------------------------------

def test_slot_feature_id_fallback_for_featureless_object():
    """feature_id falls back to repr(feature) when .id is absent."""

    async def noop():
        pass

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(noop())
        feature_no_id = types.SimpleNamespace()
        slot = ConcurrentDispatchSlot(feature=feature_no_id, task=task)
        assert slot.feature_id == repr(feature_no_id)
        loop.run_until_complete(task)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# dispatch_concurrent_features — integration smoke test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_concurrent_features_dispatches_multiple():
    """dispatch_concurrent_features dispatches multiple ready features concurrently."""
    from bob3.orchestrator_concurrent import dispatch_concurrent_features

    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)
    executed = []

    async def worker(f):
        executed.append(f.id)
        return "done"

    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        results = await dispatch_concurrent_features(loop, worker=worker)

    assert len(results) == 3
    assert all(r["success"] for r in results)
    assert set(executed) == {"feat-0", "feat-1", "feat-2"}


@pytest.mark.asyncio
async def test_dispatch_concurrent_features_empty_queue_returns_empty():
    """dispatch_concurrent_features returns [] when no ready features exist."""
    from bob3.orchestrator_concurrent import dispatch_concurrent_features

    loop = _make_loop(cap=3, ready_features=[])

    async def worker(f):
        return "done"

    with mock.patch("bob3.orchestrator.run_loop.db"):
        results = await dispatch_concurrent_features(loop, worker=worker)

    assert results == []
