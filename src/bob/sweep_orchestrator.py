"""Sweep orchestrator with cost-budget guard rails.

Dispatches multiple ablation runs in parallel (asyncio, up to
BOB_SWEEP_PARALLELISM workers), enforces a total cost budget
(BOB_SWEEP_BUDGET_USD), and writes resumable checkpoints to
.bob/sweep_checkpoint.json so an interrupted sweep can restart
from the last completed run.

Plan input is a YAML file listing variant × spec × seed combinations.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import yaml
from pydantic import BaseModel, Field

from stuck_readiness_decomposition import decompose_feature, should_trigger_decomposition

if TYPE_CHECKING:
    from bob.models import Feature

_DEFAULT_PARALLELISM = 4
_DEFAULT_BUDGET_USD = 100.0
_DEFAULT_CHECKPOINT_PATH = Path(".bob") / "sweep_checkpoint.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SweepRun(BaseModel):
    """One cell in the sweep grid: variant × spec × seed."""

    variant: str
    spec: str
    seed: int
    run_id: str = Field(default="")

    def model_post_init(self, __context: Any) -> None:
        if not self.run_id:
            key = f"{self.variant}:{self.spec}:{self.seed}"
            self.run_id = hashlib.sha256(key.encode()).hexdigest()[:16]


class SweepPlan(BaseModel):
    """Ordered list of sweep runs parsed from a YAML plan file."""

    runs: list[SweepRun] = Field(default_factory=list)


class SweepResult(BaseModel):
    """Aggregate outcome of a completed (or partially completed) sweep."""

    completed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _resolve_sweep_parallelism() -> int:
    """Return worker count from BOB_SWEEP_PARALLELISM, falling back to 4."""
    raw = os.environ.get("BOB_SWEEP_PARALLELISM", "")
    try:
        value = int(raw)
        if value > 0:
            return value
    except (ValueError, TypeError):
        pass
    return _DEFAULT_PARALLELISM


def _resolve_sweep_budget() -> float:
    """Return budget from BOB_SWEEP_BUDGET_USD, falling back to 100.0."""
    raw = os.environ.get("BOB_SWEEP_BUDGET_USD", "")
    try:
        value = float(raw)
        return value
    except (ValueError, TypeError):
        pass
    return _DEFAULT_BUDGET_USD


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def load_sweep_plan(path: str | Path) -> SweepPlan:
    """Parse a YAML sweep plan file into a SweepPlan.

    The YAML must contain a top-level ``runs`` list where each entry has
    ``variant``, ``spec``, and ``seed`` keys.

    Raises FileNotFoundError if the file does not exist.
    """
    plan_path = Path(path)
    if not plan_path.exists():
        raise FileNotFoundError(f"Sweep plan file not found: {plan_path}")

    with plan_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    runs = [SweepRun(**entry) for entry in data.get("runs", [])]
    return SweepPlan(runs=runs)


# ---------------------------------------------------------------------------
# Checkpoint I/O
# ---------------------------------------------------------------------------


def _load_checkpoint(path: Path) -> dict[str, Any]:
    """Load checkpoint state or return empty state if file missing."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"completed": [], "total_cost_usd": 0.0}


def _save_checkpoint(path: Path, completed: list[str], total_cost_usd: float) -> None:
    """Atomically write checkpoint state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"completed": completed, "total_cost_usd": total_cost_usd}),
        encoding="utf-8",
    )
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------

RunOneCallback = Callable[[SweepRun], Coroutine[Any, Any, float]]


async def run_sweep(
    plan: SweepPlan,
    *,
    run_one: RunOneCallback,
    budget_usd: float | None = None,
    checkpoint_path: Path | None = None,
) -> SweepResult:
    """Execute a sweep plan with parallelism and cost-budget guard rails.

    Args:
        plan: The SweepPlan describing all runs to execute.
        run_one: Async callable that executes a single SweepRun and returns
            the USD cost incurred by that run.
        budget_usd: Total cost budget in USD. Overrides
            BOB_SWEEP_BUDGET_USD env var when provided. When budget is
            exhausted, remaining runs are marked as skipped.
        checkpoint_path: Path for the resumable checkpoint JSON. Defaults to
            .bob/sweep_checkpoint.json relative to cwd.

    Returns:
        SweepResult with completed, failed, skipped run IDs and total cost.
    """
    effective_budget = budget_usd if budget_usd is not None else _resolve_sweep_budget()
    parallelism = _resolve_sweep_parallelism()
    ckpt_path = checkpoint_path if checkpoint_path is not None else _DEFAULT_CHECKPOINT_PATH

    ckpt = _load_checkpoint(ckpt_path)
    already_completed: set[str] = set(ckpt.get("completed", []))
    accumulated_cost: float = float(ckpt.get("total_cost_usd", 0.0))

    completed: list[str] = list(already_completed)
    failed: list[str] = []
    skipped: list[str] = []

    semaphore = asyncio.Semaphore(parallelism)
    cost_lock = asyncio.Lock()

    # Partition runs into pending (need to run) vs already done
    pending_runs = [r for r in plan.runs if r.run_id not in already_completed]

    # If budget is already exhausted before we start, skip all pending
    if accumulated_cost >= effective_budget and pending_runs:
        skipped.extend(r.run_id for r in pending_runs)
        _save_checkpoint(ckpt_path, completed, accumulated_cost)
        return SweepResult(
            completed=completed,
            failed=failed,
            skipped=skipped,
            total_cost_usd=accumulated_cost,
        )

    async def execute_one(sweep_run: SweepRun) -> None:
        nonlocal accumulated_cost

        # Check budget before acquiring the semaphore
        async with cost_lock:
            if accumulated_cost >= effective_budget:
                skipped.append(sweep_run.run_id)
                return

        async with semaphore:
            # Re-check after acquiring semaphore (another worker may have spent budget)
            async with cost_lock:
                if accumulated_cost >= effective_budget:
                    skipped.append(sweep_run.run_id)
                    return

            try:
                cost = await run_one(sweep_run)
            except Exception:
                failed.append(sweep_run.run_id)
                _save_checkpoint(ckpt_path, completed, accumulated_cost)
                return

            async with cost_lock:
                accumulated_cost += cost
                completed.append(sweep_run.run_id)

            _save_checkpoint(ckpt_path, completed, accumulated_cost)

    await asyncio.gather(*(execute_one(r) for r in pending_runs))

    return SweepResult(
        completed=completed,
        failed=failed,
        skipped=skipped,
        total_cost_usd=accumulated_cost,
    )


def apply_stuck_readiness_decomposition(
    feature: "Feature",
    *,
    previous_readiness_score: float | None = None,
    db_update: Any | None = None,
) -> "Feature | None":
    """Check if a feature is stuck and decompose it if so.

    Returns the updated feature with status ``pending_decomposition`` when
    decomposition is triggered, or None when the feature is not stuck.
    """
    if not should_trigger_decomposition(
        feature, previous_readiness_score=previous_readiness_score
    ):
        return None
    return decompose_feature(feature, db_update=db_update)
