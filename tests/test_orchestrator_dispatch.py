"""Tests for bob.orchestrator_dispatch — feature f9de5db3.

Verifies that dispatch_concurrent_features:
- Is importable from bob.orchestrator_dispatch
- Is also integrated into bob.orchestrator
- Returns empty list when no ready features exist or cap is saturated
- Correctly resolves BOB_MAX_CONCURRENT_FEATURES env var (default 3)
- Claims ready features and marks them executing before dispatch
- Runs workers concurrently (multiple features dispatch in parallel)
- Isolates failures: one bad worker does not cancel peers
- Invokes on_failure callback on worker error

AC: pytest: tests/test_orchestrator_dispatch.py
AC: integration: bob.orchestrator
"""

from __future__ import annotations

import asyncio
import inspect
import os
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
    """Build a minimal OrchestrationLoop mock with a given concurrency cap."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = cap
    loop.project_id = "proj-test-f9de5db3"
    # Return features one by one, then None to signal empty
    loop.find_next_ready_feature = mock.MagicMock(
        side_effect=list(ready_features) + [None]
    )
    return loop


# ---------------------------------------------------------------------------
# AC 1: File exists — importability from the canonical module
# ---------------------------------------------------------------------------

class TestModuleImportability:
    def test_dispatch_concurrent_features_importable(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        assert callable(dispatch_concurrent_features)

    def test_claim_ready_features_importable(self):
        from bob.orchestrator_dispatch import claim_ready_features
        assert callable(claim_ready_features)

    def test_open_dispatch_slots_importable(self):
        from bob.orchestrator_dispatch import open_dispatch_slots
        assert callable(open_dispatch_slots)

    def test_resolve_max_concurrent_features_importable(self):
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert callable(resolve_max_concurrent_features)

    def test_dispatch_concurrent_features_is_async(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        assert inspect.iscoroutinefunction(dispatch_concurrent_features)

    def test_all_exports_listed_in_dunder_all(self):
        import bob.orchestrator_dispatch as mod
        assert "dispatch_concurrent_features" in mod.__all__
        assert "claim_ready_features" in mod.__all__
        assert "open_dispatch_slots" in mod.__all__
        assert "resolve_max_concurrent_features" in mod.__all__


# ---------------------------------------------------------------------------
# AC 2: Function defined — resolve_max_concurrent_features
# ---------------------------------------------------------------------------

class TestResolveMaxConcurrentFeatures:
    def test_default_is_three(self, monkeypatch):
        monkeypatch.delenv("BOB_MAX_CONCURRENT_FEATURES", raising=False)
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert resolve_max_concurrent_features() == 3

    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "5")
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert resolve_max_concurrent_features() == 5

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "not-a-number")
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert resolve_max_concurrent_features() == 3

    def test_zero_env_clamps_to_one(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "0")
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert resolve_max_concurrent_features() == 1

    def test_negative_env_clamps_to_one(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "-2")
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert resolve_max_concurrent_features() == 1

    def test_env_one_is_accepted(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "1")
        from bob.orchestrator_dispatch import resolve_max_concurrent_features
        assert resolve_max_concurrent_features() == 1


# ---------------------------------------------------------------------------
# open_dispatch_slots
# ---------------------------------------------------------------------------

class TestOpenDispatchSlots:
    def test_full_cap_when_no_active(self):
        from bob.orchestrator_dispatch import open_dispatch_slots
        loop = mock.MagicMock()
        loop.max_concurrent_features = 3
        assert open_dispatch_slots(loop) == 3

    def test_cap_minus_active(self):
        from bob.orchestrator_dispatch import open_dispatch_slots
        loop = mock.MagicMock()
        loop.max_concurrent_features = 3
        assert open_dispatch_slots(loop, active_feature_ids={"a", "b"}) == 1

    def test_zero_when_saturated(self):
        from bob.orchestrator_dispatch import open_dispatch_slots
        loop = mock.MagicMock()
        loop.max_concurrent_features = 3
        assert open_dispatch_slots(loop, active_feature_ids={"a", "b", "c"}) == 0

    def test_zero_when_over_saturated(self):
        from bob.orchestrator_dispatch import open_dispatch_slots
        loop = mock.MagicMock()
        loop.max_concurrent_features = 2
        assert open_dispatch_slots(loop, active_feature_ids={"a", "b", "c"}) == 0

    def test_explicit_none_uses_full_cap(self):
        from bob.orchestrator_dispatch import open_dispatch_slots
        loop = mock.MagicMock()
        loop.max_concurrent_features = 4
        assert open_dispatch_slots(loop, active_feature_ids=None) == 4


# ---------------------------------------------------------------------------
# claim_ready_features
# ---------------------------------------------------------------------------

class TestClaimReadyFeatures:
    def test_returns_empty_when_no_ready(self):
        from bob.orchestrator_dispatch import claim_ready_features
        loop = _make_loop(cap=3, ready_features=[])
        with mock.patch("bob.db.update_feature") as mock_update:
            result = claim_ready_features(loop)
        assert result == []

    def test_claims_up_to_cap(self):
        from bob.orchestrator_dispatch import claim_ready_features
        features = [_make_feature(f"f{i}") for i in range(5)]
        loop = _make_loop(cap=3, ready_features=features)
        with mock.patch("bob.db.update_feature"):
            claimed = claim_ready_features(loop)
        assert len(claimed) == 3

    def test_marks_features_executing(self):
        from bob.orchestrator_dispatch import claim_ready_features
        features = [_make_feature(f"f{i}") for i in range(2)]
        loop = _make_loop(cap=3, ready_features=features)
        with mock.patch("bob.db.update_feature") as mock_update:
            claimed = claim_ready_features(loop)
        assert mock_update.call_count == len(claimed)
        for call in mock_update.call_args_list:
            # call args: (feature_id, status="executing")
            assert call[1].get("status") == "executing" or call[0][1] == "executing"

    def test_skips_already_active(self):
        from bob.orchestrator_dispatch import claim_ready_features
        f1 = _make_feature("already-in-flight")
        f2 = _make_feature("available")
        loop = _make_loop(cap=3, ready_features=[f1, f2])
        with mock.patch("bob.db.update_feature"):
            claimed = claim_ready_features(
                loop, active_feature_ids={"already-in-flight"}
            )
        claimed_ids = {f.id for f in claimed}
        assert "already-in-flight" not in claimed_ids

    def test_returns_empty_when_cap_saturated(self):
        from bob.orchestrator_dispatch import claim_ready_features
        loop = _make_loop(cap=2, ready_features=[_make_feature("f1")])
        with mock.patch("bob.db.update_feature"):
            result = claim_ready_features(
                loop, active_feature_ids={"x", "y"}
            )
        assert result == []


# ---------------------------------------------------------------------------
# AC 2: dispatch_concurrent_features behaviour
# ---------------------------------------------------------------------------

class TestDispatchConcurrentFeatures:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_ready(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        loop = _make_loop(cap=3, ready_features=[])

        async def noop(feature):
            return "done"

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(loop, worker=noop)
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_cap_saturated(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        features = [_make_feature(f"f{i}") for i in range(3)]
        loop = _make_loop(cap=3, ready_features=features)

        async def noop(feature):
            return "done"

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(
                loop,
                worker=noop,
                active_feature_ids={"x", "y", "z"},
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_dispatches_multiple_features(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        features = [_make_feature(f"feat-{i}") for i in range(3)]
        loop = _make_loop(cap=3, ready_features=features)

        executed_ids: list[str] = []

        async def worker(feature):
            executed_ids.append(feature.id)
            return feature.id

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(loop, worker=worker)

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert set(executed_ids) == {"feat-0", "feat-1", "feat-2"}

    @pytest.mark.asyncio
    async def test_result_dicts_have_required_keys(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        features = [_make_feature("f-key-test")]
        loop = _make_loop(cap=3, ready_features=features)

        async def worker(feature):
            return "ok"

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(loop, worker=worker)

        assert len(results) == 1
        r = results[0]
        assert "feature_id" in r
        assert "success" in r
        assert "result" in r
        assert "error" in r

    @pytest.mark.asyncio
    async def test_worker_failure_is_isolated(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        features = [_make_feature("bad"), _make_feature("good")]
        loop = _make_loop(cap=3, ready_features=features)

        async def worker(feature):
            if feature.id == "bad":
                raise ValueError("intentional failure")
            return "ok"

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(loop, worker=worker)

        assert len(results) == 2
        by_id = {r["feature_id"]: r for r in results}
        assert by_id["bad"]["success"] is False
        assert by_id["good"]["success"] is True

    @pytest.mark.asyncio
    async def test_on_failure_callback_invoked(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        features = [_make_feature("fail-me")]
        loop = _make_loop(cap=3, ready_features=features)

        failure_log: list[tuple] = []

        def on_fail(feature, exc):
            failure_log.append((feature.id, str(exc)))

        async def worker(feature):
            raise RuntimeError("boom")

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(
                loop, worker=worker, on_failure=on_fail
            )

        assert len(failure_log) == 1
        assert failure_log[0][0] == "fail-me"
        assert "boom" in failure_log[0][1]

    @pytest.mark.asyncio
    async def test_env_override_limits_concurrency(self, monkeypatch):
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "2")

        features = [_make_feature(f"f{i}") for i in range(5)]
        loop = _make_loop(cap=5, ready_features=features)

        running_concurrently = []
        high_water = [0]
        currently_running = [0]

        async def worker(feature):
            currently_running[0] += 1
            high_water[0] = max(high_water[0], currently_running[0])
            await asyncio.sleep(0)  # yield to allow concurrent tasks to start
            currently_running[0] -= 1
            return feature.id

        with mock.patch("bob.orchestrator_dispatch.db"):
            results = await dispatch_concurrent_features(loop, worker=worker)

        # With BOB_MAX_CONCURRENT_FEATURES=2, at most 2 workers run simultaneously
        assert high_water[0] <= 2

    @pytest.mark.asyncio
    async def test_concurrent_tasks_run_in_parallel(self, monkeypatch):
        """Multiple workers overlap in time when max_concurrent > 1."""
        from bob.orchestrator_dispatch import dispatch_concurrent_features
        monkeypatch.setenv("BOB_MAX_CONCURRENT_FEATURES", "3")

        features = [_make_feature(f"parallel-{i}") for i in range(3)]
        loop = _make_loop(cap=3, ready_features=features)

        start_times: dict[str, float] = {}
        barrier = asyncio.Event()

        async def worker(feature):
            import time
            start_times[feature.id] = time.monotonic()
            await barrier.wait()
            return feature.id

        # Set barrier after creating tasks so all workers can start
        async def run():
            task = asyncio.create_task(
                _do_dispatch(loop)
            )
            # Give workers time to start
            await asyncio.sleep(0.01)
            barrier.set()
            return await task

        async def _do_dispatch(lp):
            with mock.patch("bob.orchestrator_dispatch.db"):
                return await dispatch_concurrent_features(lp, worker=worker)

        results = await run()
        assert len(results) == 3
        # All 3 workers started before barrier lifted = truly parallel
        assert len(start_times) == 3


# ---------------------------------------------------------------------------
# AC 4: Integration — dispatch_concurrent_features accessible from bob.orchestrator
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_dispatch_concurrent_features_in_bob_orchestrator(self):
        import bob.orchestrator as orch
        assert hasattr(orch, "dispatch_concurrent_features_v2")

    def test_dispatch_concurrent_features_v2_is_callable(self):
        from bob.orchestrator import dispatch_concurrent_features_v2
        assert callable(dispatch_concurrent_features_v2)

    def test_dispatch_concurrent_features_v2_is_async(self):
        from bob.orchestrator import dispatch_concurrent_features_v2
        assert inspect.iscoroutinefunction(dispatch_concurrent_features_v2)

    def test_orchestrator_dispatch_module_importable_standalone(self):
        import bob.orchestrator_dispatch
        assert bob.orchestrator_dispatch is not None

    def test_both_dispatch_functions_have_same_signature_shape(self):
        from bob.orchestrator_dispatch import dispatch_concurrent_features as new_fn
        from bob.orchestrator.run_loop import dispatch_concurrent_features as old_fn
        new_sig = inspect.signature(new_fn)
        old_sig = inspect.signature(old_fn)
        # Both must accept loop, worker, active_feature_ids, on_failure
        for param in ("loop", "worker", "active_feature_ids", "on_failure"):
            assert param in new_sig.parameters, f"{param} missing from new function"
            assert param in old_sig.parameters, f"{param} missing from old function"
