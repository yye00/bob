"""DAG-respecting parallel orchestration loop (feature 2c4bfe0f).

Refactors the sequential OrchestrationLoop into a parallelized variant
that uses asyncio.gather with a semaphore capped at BOB3_PARALLELISM
(default 4).  All existing safety invariants are preserved:
  - each sub-agent still runs in its own subprocess
  - the underlying OrchestrationLoop.execute_feature handles commit atomicity
  - cascade_update_dependents is called after each feature completes

Termination conditions mirror run_loop.OrchestrationLoop:
  - ALL_COMPLETED  — no features remain in a non-terminal state
  - ALL_BLOCKED    — remaining features are all failed/blocked/vetoed
  - BUDGET_EXCEEDED — accumulated cost >= max_cost
  - SHUTDOWN_REQUESTED — the caller has set the shutdown_event

Performance motivation:
  serial:   20 features × 8 min = 160 min
  parallel: BOB3_PARALLELISM=4  → ~40 min on the same hardware
"""
from __future__ import annotations

import asyncio
import enum
import logging
import os
from typing import Any

from bob3 import db
from bob3.orchestrator.run_loop import OrchestrationLoop, cascade_update_dependents

logger = logging.getLogger(__name__)

_DEFAULT_PARALLELISM = 4


def _resolve_parallelism() -> int:
    """Return the effective parallelism cap.

    Reads BOB3_PARALLELISM from the environment; falls back to 4 for
    missing, non-integer, zero, or negative values.
    """
    raw = os.environ.get("BOB3_PARALLELISM")
    if raw is not None:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return _DEFAULT_PARALLELISM


class ParallelLoopTermination(enum.Enum):
    """Reason the parallel loop stopped."""

    ALL_COMPLETED = "all_completed"
    ALL_BLOCKED = "all_blocked"
    BUDGET_EXCEEDED = "budget_exceeded"
    SHUTDOWN_REQUESTED = "shutdown_requested"


async def run_parallel_loop(
    *,
    project_id: str,
    max_cost: float | None = None,
    workspace: str | None = None,
    fresh: bool = False,
    shutdown_event: asyncio.Event | None = None,
    **kwargs: Any,
) -> ParallelLoopTermination:
    """Run the orchestration loop with DAG-respecting parallel feature execution.

    Picks all currently-ready features, dispatches them concurrently under
    a semaphore capped at BOB3_PARALLELISM, calls cascade_update_dependents
    after each completes, and repeats until a termination condition is met.

    Args:
        project_id: The project to orchestrate.
        max_cost: Optional per-run cost ceiling in USD.
        workspace: Optional workspace path override forwarded to the inner loop.
        fresh: Whether to start from a fresh workspace snapshot.
        shutdown_event: Optional asyncio.Event; when set the loop exits with
            SHUTDOWN_REQUESTED (checked before each dispatch cycle).
        **kwargs: Forwarded verbatim to OrchestrationLoop.__init__.

    Returns:
        A ParallelLoopTermination value indicating why the loop stopped.
    """
    parallelism = _resolve_parallelism()
    semaphore = asyncio.Semaphore(parallelism)

    loop = OrchestrationLoop(
        project_id=project_id,
        max_cost=max_cost,
        workspace=workspace or "",
        fresh=fresh,
        **kwargs,
    )

    async def _run_one(feature: Any) -> None:
        """Execute a single feature under the semaphore and cascade afterwards."""
        async with semaphore:
            await loop.execute_feature(feature)
        cascade_update_dependents(feature.id)

    while True:
        # Honour shutdown signal before starting a new dispatch cycle.
        if shutdown_event is not None and shutdown_event.is_set():
            logger.info("Shutdown requested; stopping parallel loop")
            return ParallelLoopTermination.SHUTDOWN_REQUESTED

        if loop.budget_exceeded():
            logger.info("Budget exceeded; stopping parallel loop")
            return ParallelLoopTermination.BUDGET_EXCEEDED

        ready_features = db.get_ready_features(project_id)

        if not ready_features:
            # Determine whether we finished or are stuck.
            all_features = db.list_features(project_id=project_id)
            if not all_features:
                return ParallelLoopTermination.ALL_COMPLETED

            terminal_statuses = {
                "completed",
                "skipped",
                "cancelled",
                "failed",
                "needs_human",
                "vetoed",
                "blocked",
                "interrupted",
            }
            all_terminal = all(f.status in terminal_statuses for f in all_features)
            all_done = all(
                f.status in {"completed", "skipped", "cancelled"} for f in all_features
            )

            if all_done:
                return ParallelLoopTermination.ALL_COMPLETED
            if all_terminal:
                return ParallelLoopTermination.ALL_BLOCKED
            return ParallelLoopTermination.ALL_COMPLETED

        # Dispatch the current wave of ready features in parallel.
        tasks = [asyncio.create_task(_run_one(f)) for f in ready_features]
        await asyncio.gather(*tasks, return_exceptions=True)
