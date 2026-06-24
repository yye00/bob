"""Tests for src/bob/orchestrator/parallel_loop.py (feature 2c4bfe0f).

Covers run_parallel_loop: DAG-respecting parallel execution with a
semaphore capped at BOB_PARALLELISM (default 4).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.orchestrator.parallel_loop import (
    ParallelLoopTermination,
    _resolve_parallelism,
    run_parallel_loop,
)


# ---------------------------------------------------------------------------
# Unit: _resolve_parallelism
# ---------------------------------------------------------------------------


class TestResolveParallelism:
    def test_default_is_4(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("BOB_PARALLELISM", None)
            assert _resolve_parallelism() == 4

    def test_env_override(self):
        with patch.dict(os.environ, {"BOB_PARALLELISM": "8"}):
            assert _resolve_parallelism() == 8

    def test_env_invalid_falls_back_to_default(self):
        with patch.dict(os.environ, {"BOB_PARALLELISM": "abc"}):
            assert _resolve_parallelism() == 4

    def test_env_zero_falls_back_to_default(self):
        with patch.dict(os.environ, {"BOB_PARALLELISM": "0"}):
            assert _resolve_parallelism() == 4

    def test_env_negative_falls_back_to_default(self):
        with patch.dict(os.environ, {"BOB_PARALLELISM": "-2"}):
            assert _resolve_parallelism() == 4

    def test_env_one_is_valid(self):
        with patch.dict(os.environ, {"BOB_PARALLELISM": "1"}):
            assert _resolve_parallelism() == 1


# ---------------------------------------------------------------------------
# Unit: ParallelLoopTermination enum
# ---------------------------------------------------------------------------


class TestParallelLoopTermination:
    def test_has_all_completed(self):
        assert ParallelLoopTermination.ALL_COMPLETED.value == "all_completed"

    def test_has_all_blocked(self):
        assert ParallelLoopTermination.ALL_BLOCKED.value == "all_blocked"

    def test_has_budget_exceeded(self):
        assert ParallelLoopTermination.BUDGET_EXCEEDED.value == "budget_exceeded"

    def test_has_shutdown_requested(self):
        assert ParallelLoopTermination.SHUTDOWN_REQUESTED.value == "shutdown_requested"


# ---------------------------------------------------------------------------
# Integration: run_parallel_loop
# ---------------------------------------------------------------------------


def _make_feature(fid: str, name: str, status: str = "ready") -> MagicMock:
    f = MagicMock()
    f.id = fid
    f.name = name
    f.status = status
    f.readiness_score = 0.9
    f.risk_category = "low"
    f.research_iterations = 0
    return f


class TestRunParallelLoopNoFeatures:
    @pytest.mark.asyncio
    async def test_no_ready_features_all_completed(self):
        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
        ):
            mock_db.get_ready_features.return_value = []
            mock_db.list_features.return_value = []

            result = await run_parallel_loop(project_id="proj-1")

        assert result == ParallelLoopTermination.ALL_COMPLETED

    @pytest.mark.asyncio
    async def test_no_ready_features_all_blocked(self):
        blocked = _make_feature("f1", "blocked", status="failed")
        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
        ):
            mock_db.get_ready_features.return_value = []
            mock_db.list_features.return_value = [blocked]

            result = await run_parallel_loop(project_id="proj-1")

        assert result == ParallelLoopTermination.ALL_BLOCKED


class TestRunParallelLoopBudget:
    @pytest.mark.asyncio
    async def test_budget_exceeded_before_execution(self):
        feature = _make_feature("f1", "feat1")
        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
            patch(
                "bob.orchestrator.parallel_loop.OrchestrationLoop"
            ) as MockLoop,
        ):
            mock_db.get_ready_features.return_value = [feature]
            mock_db.list_features.return_value = [feature]
            loop_instance = MagicMock()
            loop_instance.budget_exceeded.return_value = True
            MockLoop.return_value = loop_instance

            result = await run_parallel_loop(
                project_id="proj-1", max_cost=0.001
            )

        assert result == ParallelLoopTermination.BUDGET_EXCEEDED


class TestRunParallelLoopExecution:
    @pytest.mark.asyncio
    async def test_single_feature_executed_and_completed(self):
        feature = _make_feature("f1", "feature-1")
        executed_ids: list[str] = []

        async def fake_execute(f):
            executed_ids.append(f.id)
            return MagicMock()

        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
            patch(
                "bob.orchestrator.parallel_loop.OrchestrationLoop"
            ) as MockLoop,
        ):
            # First call: feature is ready; second call: all done
            mock_db.get_ready_features.side_effect = [[feature], []]
            mock_db.list_features.return_value = []
            loop_instance = MagicMock()
            loop_instance.budget_exceeded.return_value = False
            loop_instance.execute_feature = AsyncMock(side_effect=fake_execute)
            MockLoop.return_value = loop_instance

            result = await run_parallel_loop(project_id="proj-1")

        assert result == ParallelLoopTermination.ALL_COMPLETED
        assert "f1" in executed_ids

    @pytest.mark.asyncio
    async def test_parallelism_capped_by_semaphore(self):
        """All 4 features are run concurrently (semaphore cap = 4, N=4)."""
        features = [_make_feature(f"f{i}", f"feat-{i}") for i in range(4)]
        concurrent_max = 0
        running = 0

        async def fake_execute(f):
            nonlocal concurrent_max, running
            running += 1
            concurrent_max = max(concurrent_max, running)
            await asyncio.sleep(0.01)  # yield to allow concurrency
            running -= 1
            return MagicMock()

        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
            patch(
                "bob.orchestrator.parallel_loop.OrchestrationLoop"
            ) as MockLoop,
            patch.dict(os.environ, {"BOB_PARALLELISM": "4"}),
        ):
            mock_db.get_ready_features.side_effect = [features, []]
            mock_db.list_features.return_value = []
            loop_instance = MagicMock()
            loop_instance.budget_exceeded.return_value = False
            loop_instance.execute_feature = AsyncMock(side_effect=fake_execute)
            MockLoop.return_value = loop_instance

            result = await run_parallel_loop(project_id="proj-1")

        assert result == ParallelLoopTermination.ALL_COMPLETED
        assert concurrent_max >= 2  # at least 2 ran concurrently

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """With BOB_PARALLELISM=1, only 1 feature runs at a time."""
        features = [_make_feature(f"f{i}", f"feat-{i}") for i in range(3)]
        concurrent_max = 0
        running = 0

        async def fake_execute(f):
            nonlocal concurrent_max, running
            running += 1
            concurrent_max = max(concurrent_max, running)
            await asyncio.sleep(0.01)
            running -= 1
            return MagicMock()

        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
            patch(
                "bob.orchestrator.parallel_loop.OrchestrationLoop"
            ) as MockLoop,
            patch.dict(os.environ, {"BOB_PARALLELISM": "1"}),
        ):
            mock_db.get_ready_features.side_effect = [features, []]
            mock_db.list_features.return_value = []
            loop_instance = MagicMock()
            loop_instance.budget_exceeded.return_value = False
            loop_instance.execute_feature = AsyncMock(side_effect=fake_execute)
            MockLoop.return_value = loop_instance

            result = await run_parallel_loop(project_id="proj-1")

        assert result == ParallelLoopTermination.ALL_COMPLETED
        assert concurrent_max == 1  # strict serialization

    @pytest.mark.asyncio
    async def test_shutdown_flag_stops_loop(self):
        features = [_make_feature("f1", "feat-1")]
        executed: list[str] = []

        async def fake_execute(f):
            executed.append(f.id)
            return MagicMock()

        shutdown_event = asyncio.Event()
        shutdown_event.set()  # already signalled

        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
            patch(
                "bob.orchestrator.parallel_loop.OrchestrationLoop"
            ) as MockLoop,
        ):
            mock_db.get_ready_features.return_value = features
            mock_db.list_features.return_value = features
            loop_instance = MagicMock()
            loop_instance.budget_exceeded.return_value = False
            loop_instance.execute_feature = AsyncMock(side_effect=fake_execute)
            MockLoop.return_value = loop_instance

            result = await run_parallel_loop(
                project_id="proj-1",
                shutdown_event=shutdown_event,
            )

        assert result == ParallelLoopTermination.SHUTDOWN_REQUESTED

    @pytest.mark.asyncio
    async def test_cascade_called_after_feature_completes(self):
        """cascade_update_dependents is called once per completed feature."""
        feature = _make_feature("f1", "feat-1")
        cascaded: list[str] = []

        async def fake_execute(f):
            return MagicMock()

        with (
            patch("bob.orchestrator.parallel_loop.db") as mock_db,
            patch(
                "bob.orchestrator.parallel_loop.OrchestrationLoop"
            ) as MockLoop,
            patch(
                "bob.orchestrator.parallel_loop.cascade_update_dependents"
            ) as mock_cascade,
        ):
            mock_db.get_ready_features.side_effect = [[feature], []]
            mock_db.list_features.return_value = []
            loop_instance = MagicMock()
            loop_instance.budget_exceeded.return_value = False
            loop_instance.execute_feature = AsyncMock(side_effect=fake_execute)
            MockLoop.return_value = loop_instance
            mock_cascade.side_effect = lambda fid: cascaded.append(fid) or []

            result = await run_parallel_loop(project_id="proj-1")

        assert result == ParallelLoopTermination.ALL_COMPLETED
        assert "f1" in cascaded
