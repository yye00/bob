"""Tests for src/bob3/sweep_orchestrator.py

Covers: SweepPlan, SweepResult, SweepRun, run_sweep
- Parallel dispatch with BOB3_SWEEP_PARALLELISM cap
- Cost-budget enforcement via BOB3_SWEEP_BUDGET_USD
- Resumable checkpoints written to .bob3/sweep_checkpoint.json
- YAML plan loading
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from bob3.sweep_orchestrator import (
    SweepPlan,
    SweepResult,
    SweepRun,
    load_sweep_plan,
    run_sweep,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


MINIMAL_PLAN_DICT: dict[str, Any] = {
    "runs": [
        {"variant": "V0", "spec": "spec_a", "seed": 1},
        {"variant": "V1", "spec": "spec_a", "seed": 2},
        {"variant": "V0", "spec": "spec_b", "seed": 1},
    ]
}


def make_plan(runs: list[dict[str, Any]] | None = None) -> SweepPlan:
    if runs is None:
        runs = MINIMAL_PLAN_DICT["runs"]
    return SweepPlan(runs=[SweepRun(**r) for r in runs])


# ---------------------------------------------------------------------------
# SweepRun
# ---------------------------------------------------------------------------


class TestSweepRun:
    def test_fields_stored(self):
        run = SweepRun(variant="V0", spec="spec_a", seed=42)
        assert run.variant == "V0"
        assert run.spec == "spec_a"
        assert run.seed == 42

    def test_run_id_generated(self):
        run = SweepRun(variant="V0", spec="spec_a", seed=1)
        assert isinstance(run.run_id, str)
        assert len(run.run_id) > 0

    def test_run_id_deterministic_from_fields(self):
        r1 = SweepRun(variant="V0", spec="spec_a", seed=1)
        r2 = SweepRun(variant="V0", spec="spec_a", seed=1)
        assert r1.run_id == r2.run_id

    def test_run_id_differs_by_field(self):
        r1 = SweepRun(variant="V0", spec="spec_a", seed=1)
        r2 = SweepRun(variant="V1", spec="spec_a", seed=1)
        assert r1.run_id != r2.run_id


# ---------------------------------------------------------------------------
# SweepPlan
# ---------------------------------------------------------------------------


class TestSweepPlan:
    def test_plan_stores_runs(self):
        plan = make_plan()
        assert len(plan.runs) == 3

    def test_plan_runs_are_sweep_run_instances(self):
        plan = make_plan()
        for r in plan.runs:
            assert isinstance(r, SweepRun)

    def test_empty_runs_allowed(self):
        plan = SweepPlan(runs=[])
        assert plan.runs == []


# ---------------------------------------------------------------------------
# SweepResult
# ---------------------------------------------------------------------------


class TestSweepResult:
    def test_result_has_completed(self):
        r = SweepResult(completed=["id1"], failed=[], skipped=[])
        assert r.completed == ["id1"]

    def test_result_has_failed(self):
        r = SweepResult(completed=[], failed=["id2"], skipped=[])
        assert r.failed == ["id2"]

    def test_result_has_skipped(self):
        r = SweepResult(completed=[], failed=[], skipped=["id3"])
        assert r.skipped == ["id3"]

    def test_result_has_total_cost(self):
        r = SweepResult(completed=[], failed=[], skipped=[], total_cost_usd=1.23)
        assert r.total_cost_usd == pytest.approx(1.23)

    def test_total_cost_defaults_to_zero(self):
        r = SweepResult(completed=[], failed=[], skipped=[])
        assert r.total_cost_usd == 0.0


# ---------------------------------------------------------------------------
# load_sweep_plan – YAML loading
# ---------------------------------------------------------------------------


class TestLoadSweepPlan:
    def test_loads_valid_yaml(self, tmp_path: Path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(MINIMAL_PLAN_DICT))
        plan = load_sweep_plan(plan_file)
        assert isinstance(plan, SweepPlan)
        assert len(plan.runs) == 3

    def test_loaded_runs_have_correct_fields(self, tmp_path: Path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(MINIMAL_PLAN_DICT))
        plan = load_sweep_plan(plan_file)
        first = plan.runs[0]
        assert first.variant == "V0"
        assert first.spec == "spec_a"
        assert first.seed == 1

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_sweep_plan(tmp_path / "nonexistent.yaml")

    def test_accepts_path_string(self, tmp_path: Path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(MINIMAL_PLAN_DICT))
        plan = load_sweep_plan(str(plan_file))
        assert isinstance(plan, SweepPlan)


# ---------------------------------------------------------------------------
# run_sweep – parallelism
# ---------------------------------------------------------------------------


class TestRunSweepParallelism:
    @pytest.mark.asyncio
    async def test_all_runs_executed(self, tmp_path: Path):
        plan = make_plan()
        executed_ids: list[str] = []

        async def fake_run_one(sweep_run: SweepRun) -> float:
            executed_ids.append(sweep_run.run_id)
            return 0.01

        result = await run_sweep(
            plan,
            run_one=fake_run_one,
            checkpoint_path=tmp_path / "ckpt.json",
        )

        assert len(executed_ids) == 3
        assert len(result.completed) == 3

    @pytest.mark.asyncio
    async def test_parallelism_env_limits_concurrency(self, tmp_path: Path):
        """With BOB3_SWEEP_PARALLELISM=1, runs execute sequentially."""
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": i} for i in range(3)])
        concurrent_max = 0
        running = 0

        async def fake_run_one(run: SweepRun) -> float:
            nonlocal concurrent_max, running
            running += 1
            concurrent_max = max(concurrent_max, running)
            await asyncio.sleep(0.01)
            running -= 1
            return 0.0

        with patch.dict(os.environ, {"BOB3_SWEEP_PARALLELISM": "1"}):
            await run_sweep(
                plan,
                run_one=fake_run_one,
                checkpoint_path=tmp_path / "ckpt.json",
            )

        assert concurrent_max == 1

    @pytest.mark.asyncio
    async def test_parallelism_default_allows_concurrent_runs(self, tmp_path: Path):
        """Default parallelism allows more than 1 concurrent run."""
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": i} for i in range(4)])
        concurrent_max = 0
        running = 0

        async def fake_run_one(run: SweepRun) -> float:
            nonlocal concurrent_max, running
            running += 1
            concurrent_max = max(concurrent_max, running)
            await asyncio.sleep(0.02)
            running -= 1
            return 0.0

        with patch.dict(os.environ, {"BOB3_SWEEP_PARALLELISM": "4"}, clear=False):
            await run_sweep(
                plan,
                run_one=fake_run_one,
                checkpoint_path=tmp_path / "ckpt.json",
            )

        assert concurrent_max >= 2


# ---------------------------------------------------------------------------
# run_sweep – cost budget
# ---------------------------------------------------------------------------


class TestRunSweepBudget:
    @pytest.mark.asyncio
    async def test_budget_zero_skips_all_runs(self, tmp_path: Path):
        plan = make_plan()
        executed: list[str] = []

        async def fake_run_one(run: SweepRun) -> float:
            executed.append(run.run_id)
            return 0.5

        result = await run_sweep(
            plan,
            run_one=fake_run_one,
            budget_usd=0.0,
            checkpoint_path=tmp_path / "ckpt.json",
        )

        assert len(result.skipped) == 3
        assert len(executed) == 0

    @pytest.mark.asyncio
    async def test_budget_exceeded_mid_sweep_stops_remaining(self, tmp_path: Path):
        """After each run the accumulated cost is checked; if it exceeds
        budget the remaining enqueued runs are skipped."""
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": i} for i in range(5)])
        executed: list[str] = []

        async def fake_run_one(run: SweepRun) -> float:
            executed.append(run.run_id)
            return 0.4  # each run costs $0.40

        # Budget $0.50 — after first run ($0.40) next would exceed, so only 1 executes
        result = await run_sweep(
            plan,
            run_one=fake_run_one,
            budget_usd=0.5,
            checkpoint_path=tmp_path / "ckpt.json",
        )

        # At least some are skipped due to budget
        assert len(result.skipped) > 0
        assert result.total_cost_usd <= 1.0  # sanity: shouldn't massively overshoot

    @pytest.mark.asyncio
    async def test_budget_env_var_used_when_no_param(self, tmp_path: Path):
        """BOB3_SWEEP_BUDGET_USD is respected when budget_usd is not passed."""
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": i} for i in range(5)])
        executed: list[str] = []

        async def fake_run_one(run: SweepRun) -> float:
            executed.append(run.run_id)
            return 1.0

        with patch.dict(os.environ, {"BOB3_SWEEP_BUDGET_USD": "0.0"}):
            result = await run_sweep(
                plan,
                run_one=fake_run_one,
                checkpoint_path=tmp_path / "ckpt.json",
            )

        assert len(result.skipped) == 5
        assert len(executed) == 0

    @pytest.mark.asyncio
    async def test_total_cost_aggregated_in_result(self, tmp_path: Path):
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": i} for i in range(3)])

        async def fake_run_one(run: SweepRun) -> float:
            return 0.1

        result = await run_sweep(
            plan,
            run_one=fake_run_one,
            checkpoint_path=tmp_path / "ckpt.json",
        )

        assert result.total_cost_usd == pytest.approx(0.3, abs=0.01)


# ---------------------------------------------------------------------------
# run_sweep – checkpointing
# ---------------------------------------------------------------------------


class TestRunSweepCheckpoints:
    @pytest.mark.asyncio
    async def test_checkpoint_written_after_each_run(self, tmp_path: Path):
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": i} for i in range(2)])
        ckpt_path = tmp_path / "ckpt.json"

        async def fake_run_one(run: SweepRun) -> float:
            return 0.0

        await run_sweep(plan, run_one=fake_run_one, checkpoint_path=ckpt_path)

        assert ckpt_path.exists()
        data = json.loads(ckpt_path.read_text())
        assert "completed" in data

    @pytest.mark.asyncio
    async def test_completed_runs_in_checkpoint(self, tmp_path: Path):
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": 1}])
        ckpt_path = tmp_path / "ckpt.json"
        run_id = plan.runs[0].run_id

        async def fake_run_one(run: SweepRun) -> float:
            return 0.0

        await run_sweep(plan, run_one=fake_run_one, checkpoint_path=ckpt_path)

        data = json.loads(ckpt_path.read_text())
        assert run_id in data["completed"]

    @pytest.mark.asyncio
    async def test_resume_skips_completed_runs(self, tmp_path: Path):
        """If checkpoint shows run_id already completed, that run is skipped."""
        plan = make_plan(runs=[
            {"variant": "V0", "spec": "s", "seed": 1},
            {"variant": "V0", "spec": "s", "seed": 2},
        ])
        ckpt_path = tmp_path / "ckpt.json"
        first_run_id = plan.runs[0].run_id

        # Pre-populate checkpoint with first run completed
        ckpt_path.write_text(json.dumps({"completed": [first_run_id], "total_cost_usd": 0.05}))

        executed_ids: list[str] = []

        async def fake_run_one(run: SweepRun) -> float:
            executed_ids.append(run.run_id)
            return 0.0

        result = await run_sweep(plan, run_one=fake_run_one, checkpoint_path=ckpt_path)

        # First run was in checkpoint so should not re-execute
        assert first_run_id not in executed_ids
        # Second run should execute
        assert plan.runs[1].run_id in executed_ids
        # Checkpoint's completed run counted in result
        assert first_run_id in result.completed

    @pytest.mark.asyncio
    async def test_checkpoint_default_path_is_bob3_dir(self, tmp_path: Path):
        """When checkpoint_path is None, defaults to .bob3/sweep_checkpoint.json."""
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": 1}])

        async def fake_run_one(run: SweepRun) -> float:
            return 0.0

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".bob3").mkdir(exist_ok=True)
            await run_sweep(plan, run_one=fake_run_one)
        finally:
            os.chdir(original_dir)

        assert (tmp_path / ".bob3" / "sweep_checkpoint.json").exists()


# ---------------------------------------------------------------------------
# run_sweep – failed runs
# ---------------------------------------------------------------------------


class TestRunSweepFailures:
    @pytest.mark.asyncio
    async def test_failed_run_captured_in_result(self, tmp_path: Path):
        plan = make_plan(runs=[
            {"variant": "V0", "spec": "s", "seed": 1},
            {"variant": "V0", "spec": "s", "seed": 2},
        ])
        failing_id = plan.runs[0].run_id

        async def fake_run_one(run: SweepRun) -> float:
            if run.run_id == failing_id:
                raise RuntimeError("ablation crashed")
            return 0.0

        result = await run_sweep(
            plan,
            run_one=fake_run_one,
            checkpoint_path=tmp_path / "ckpt.json",
        )

        assert failing_id in result.failed
        assert plan.runs[1].run_id in result.completed

    @pytest.mark.asyncio
    async def test_failed_run_not_in_completed(self, tmp_path: Path):
        plan = make_plan(runs=[{"variant": "V0", "spec": "s", "seed": 1}])

        async def fake_run_one(run: SweepRun) -> float:
            raise ValueError("boom")

        result = await run_sweep(
            plan,
            run_one=fake_run_one,
            checkpoint_path=tmp_path / "ckpt.json",
        )

        assert len(result.failed) == 1
        assert len(result.completed) == 0


# ---------------------------------------------------------------------------
# _resolve_sweep_parallelism helper (via env)
# ---------------------------------------------------------------------------


class TestResolveSweepParallelism:
    def test_default_parallelism(self):
        from bob3.sweep_orchestrator import _resolve_sweep_parallelism

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BOB3_SWEEP_PARALLELISM", None)
            assert _resolve_sweep_parallelism() >= 1

    def test_env_override(self):
        from bob3.sweep_orchestrator import _resolve_sweep_parallelism

        with patch.dict(os.environ, {"BOB3_SWEEP_PARALLELISM": "6"}):
            assert _resolve_sweep_parallelism() == 6

    def test_invalid_env_falls_back_to_default(self):
        from bob3.sweep_orchestrator import _resolve_sweep_parallelism

        with patch.dict(os.environ, {"BOB3_SWEEP_PARALLELISM": "bad"}):
            assert _resolve_sweep_parallelism() >= 1

    def test_zero_env_falls_back_to_default(self):
        from bob3.sweep_orchestrator import _resolve_sweep_parallelism

        with patch.dict(os.environ, {"BOB3_SWEEP_PARALLELISM": "0"}):
            assert _resolve_sweep_parallelism() >= 1


# ---------------------------------------------------------------------------
# _resolve_sweep_budget helper (via env)
# ---------------------------------------------------------------------------


class TestResolveSweepBudget:
    def test_default_budget_is_positive(self):
        from bob3.sweep_orchestrator import _resolve_sweep_budget

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BOB3_SWEEP_BUDGET_USD", None)
            assert _resolve_sweep_budget() > 0

    def test_env_override(self):
        from bob3.sweep_orchestrator import _resolve_sweep_budget

        with patch.dict(os.environ, {"BOB3_SWEEP_BUDGET_USD": "25.0"}):
            assert _resolve_sweep_budget() == pytest.approx(25.0)

    def test_invalid_env_falls_back_to_default(self):
        from bob3.sweep_orchestrator import _resolve_sweep_budget

        with patch.dict(os.environ, {"BOB3_SWEEP_BUDGET_USD": "not_a_float"}):
            assert _resolve_sweep_budget() > 0
