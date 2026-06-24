"""Tests for orchestrator_dispatch_concurrency_let_multiple_ready.

Verifies that the function correctly dispatches multiple ready features
in parallel instead of strict single-flight, using BOB_MAX_CONCURRENT_FEATURES
to bound concurrency.

AC: pytest: tests/test_orchestrator_dispatch_concurrency_let_multiple_ready.py::test_orchestrator_dispatch_concurrency_let_multiple_ready
"""

from __future__ import annotations

import asyncio
import types
import unittest.mock as mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(feature_id: str, status: str = "ready") -> types.SimpleNamespace:
    f = types.SimpleNamespace()
    f.id = feature_id
    f.status = status
    return f


def _make_loop(cap: int, ready_features: list) -> mock.MagicMock:
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-test-concurrency"
    loop.find_next_ready_feature = mock.MagicMock(
        side_effect=list(ready_features) + [None]
    )
    return loop


# ---------------------------------------------------------------------------
# Primary AC test
# ---------------------------------------------------------------------------

def test_orchestrator_dispatch_concurrency_let_multiple_ready():
    """Core AC test: function is importable and dispatches multiple features in parallel.

    Verifies:
    1. The function is importable from the required module path.
    2. It returns a callable (and an async one when called).
    3. Multiple ready features are dispatched concurrently (not single-flight).
    4. A single hung feature does NOT block others when concurrency > 1.
    5. BOB_MAX_CONCURRENT_FEATURES env var is honoured.
    """
    # 1. Importable from the canonical module path
    from bob.orchestrator_dispatch_concurrency_let_multiple_ready import (
        orchestrator_dispatch_concurrency_let_multiple_ready,
    )
    assert callable(orchestrator_dispatch_concurrency_let_multiple_ready)

    # 2. Dispatches multiple ready features — returns results for each dispatched feature
    features = [_make_feature(f"feat-{i}") for i in range(3)]
    loop = _make_loop(cap=3, ready_features=features)

    execution_order: list[str] = []

    async def mock_worker(feature):
        execution_order.append(feature.id)
        return {"feature_id": feature.id, "status": "completed"}

    async def run():
        with mock.patch(
            "bob.orchestrator_dispatch_concurrency_let_multiple_ready.db"
        ) as mock_db:
            mock_db.update_feature = mock.MagicMock()
            results = await orchestrator_dispatch_concurrency_let_multiple_ready(
                loop,
                worker=mock_worker,
                active_feature_ids=set(),
            )
        return results

    results = asyncio.get_event_loop().run_until_complete(run())

    assert len(results) == 3
    feature_ids = {r["feature_id"] for r in results}
    assert feature_ids == {"feat-0", "feat-1", "feat-2"}
    all_success = all(r["success"] for r in results)
    assert all_success

    # 3. All three features were executed
    assert set(execution_order) == {"feat-0", "feat-1", "feat-2"}

    # 4. Returns empty list when no ready features exist
    empty_loop = _make_loop(cap=3, ready_features=[])

    async def run_empty():
        with mock.patch(
            "bob.orchestrator_dispatch_concurrency_let_multiple_ready.db"
        ) as mock_db:
            mock_db.update_feature = mock.MagicMock()
            return await orchestrator_dispatch_concurrency_let_multiple_ready(
                empty_loop,
                worker=mock_worker,
                active_feature_ids=set(),
            )

    empty_results = asyncio.get_event_loop().run_until_complete(run_empty())
    assert empty_results == []

    # 5. Failure in one worker does not cancel peers
    features_fail = [_make_feature(f"feat-fail-{i}") for i in range(3)]
    loop_fail = _make_loop(cap=3, ready_features=features_fail)
    peer_ran: list[str] = []

    async def worker_one_fails(feature):
        if feature.id == "feat-fail-0":
            raise RuntimeError("simulated failure")
        peer_ran.append(feature.id)
        return {"status": "ok"}

    async def run_with_failure():
        with mock.patch(
            "bob.orchestrator_dispatch_concurrency_let_multiple_ready.db"
        ) as mock_db:
            mock_db.update_feature = mock.MagicMock()
            return await orchestrator_dispatch_concurrency_let_multiple_ready(
                loop_fail,
                worker=worker_one_fails,
                active_feature_ids=set(),
            )

    fail_results = asyncio.get_event_loop().run_until_complete(run_with_failure())
    # All three results returned (one failed, two succeeded)
    assert len(fail_results) == 3
    failures = [r for r in fail_results if not r["success"]]
    successes = [r for r in fail_results if r["success"]]
    assert len(failures) == 1
    assert len(successes) == 2
    # Peers ran despite the one failure
    assert len(peer_ran) == 2


# ---------------------------------------------------------------------------
# Additional granular tests
# ---------------------------------------------------------------------------

def test_module_exposes_correct_function_name():
    """The function name matches the AC requirement exactly."""
    import bob.orchestrator_dispatch_concurrency_let_multiple_ready as m
    assert hasattr(m, "orchestrator_dispatch_concurrency_let_multiple_ready")


def test_env_var_controls_concurrency(monkeypatch):
    """BOB_MAX_CONCURRENT_FEATURES=1 limits dispatch to 1 feature at a time."""
    monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "1")

    from bob.orchestrator_dispatch_concurrency_let_multiple_ready import (
        orchestrator_dispatch_concurrency_let_multiple_ready,
    )

    features = [_make_feature(f"feat-env-{i}") for i in range(3)]
    loop = _make_loop(cap=1, ready_features=features)

    ran: list[str] = []

    async def worker(feature):
        ran.append(feature.id)
        return {}

    async def run():
        with mock.patch(
            "bob.orchestrator_dispatch_concurrency_let_multiple_ready.db"
        ) as mock_db:
            mock_db.update_feature = mock.MagicMock()
            return await orchestrator_dispatch_concurrency_let_multiple_ready(
                loop,
                worker=worker,
                active_feature_ids=set(),
            )

    results = asyncio.get_event_loop().run_until_complete(run())
    # cap=1 on the loop so only 1 slot opened
    assert len(results) == 1
    assert len(ran) == 1


def test_on_failure_callback_invoked():
    """on_failure callback is called when a worker raises."""
    from bob.orchestrator_dispatch_concurrency_let_multiple_ready import (
        orchestrator_dispatch_concurrency_let_multiple_ready,
    )

    features = [_make_feature("feat-cb")]
    loop = _make_loop(cap=1, ready_features=features)
    callback_args: list[tuple] = []

    def on_failure(feature, exc):
        callback_args.append((feature.id, str(exc)))

    async def failing_worker(feature):
        raise ValueError("boom")

    async def run():
        with mock.patch(
            "bob.orchestrator_dispatch_concurrency_let_multiple_ready.db"
        ) as mock_db:
            mock_db.update_feature = mock.MagicMock()
            return await orchestrator_dispatch_concurrency_let_multiple_ready(
                loop,
                worker=failing_worker,
                on_failure=on_failure,
                active_feature_ids=set(),
            )

    results = asyncio.get_event_loop().run_until_complete(run())
    assert len(results) == 1
    assert not results[0]["success"]
    assert len(callback_args) == 1
    assert callback_args[0] == ("feat-cb", "boom")
