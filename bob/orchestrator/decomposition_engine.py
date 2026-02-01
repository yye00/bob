"""
Decomposition Engine — Recursive confidence-driven work processor.
==================================================================

One algorithm, applied to everything:

    process(unit, threshold):
        confidence = evaluate(unit)
        if confidence >= threshold:
            execute(unit)
        else:
            children = decompose(unit)
            for child in children:
                process(child, threshold)

The engine manages the work unit tree, dispatches to the right
decomposer based on kind, tracks the decomposition history,
and enforces the context budget constraint.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from bob.orchestrator.work_unit import (
    WorkUnit,
    WorkUnitKind,
    WorkUnitStatus,
    ConfidenceScore,
)
from bob.orchestrator.decomposer import Decomposer
from bob.orchestrator.dag_validator import (
    validate_work_unit_dag,
    validate_task_dependencies,
)
from bob.observability.logger import EventType, create_logger
from bob.observability.telemetry import RunTelemetry


class DecompositionEngine:
    """Recursive confidence-driven decomposition engine.

    Processes work units by evaluating confidence, decomposing if below
    threshold, and executing when ready. Same pattern for tasks,
    verification, and research — just different decomposers.

    Attributes:
        decomposers: Registry of kind → Decomposer
        threshold: Confidence threshold (default 0.9)
        context_budget_pct: Max context window usage per unit (default 0.4 = 40%)
        context_window_tokens: Model's total context window size
        max_total_units: Safety limit on total work units
        tree: All work units, indexed by ID
        history: Log of engine actions for auditability
    """

    def __init__(
        self,
        threshold: float = 0.9,
        context_budget_pct: float = 0.4,
        context_window_tokens: int = 200_000,
        max_total_units: int = 100,
        output_dir: Optional[Path] = None,
    ):
        self.decomposers: dict[WorkUnitKind, Decomposer] = {}
        self.threshold = threshold
        self.context_budget_pct = context_budget_pct
        self.context_window_tokens = context_window_tokens
        self.context_budget_tokens = int(context_window_tokens * context_budget_pct)
        self.max_total_units = max_total_units
        self.max_concurrent = 4  # Limit concurrent Claude calls
        self.output_dir = output_dir

        # State
        self.tree: dict[str, WorkUnit] = {}
        self.history: list[dict[str, Any]] = []
        self._start_time: float = 0

        # Observability
        self.logger = create_logger("decomposition", project_workspace=output_dir)
        self.telemetry: Optional[RunTelemetry] = None
        if output_dir:
            self.telemetry = RunTelemetry(workspace=output_dir)

    def register(self, kind: WorkUnitKind, decomposer: Decomposer) -> None:
        """Register a decomposer for a work unit kind."""
        self.decomposers[kind] = decomposer

    def _log(self, action: str, unit_id: str, **kwargs) -> None:
        """Log an engine action for auditability."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": round(time.time() - self._start_time, 1),
            "action": action,
            "unit_id": unit_id,
            **kwargs,
        }
        self.history.append(entry)

    def _get_decomposer(self, kind: WorkUnitKind) -> Decomposer:
        """Get the decomposer for a work unit kind."""
        if kind not in self.decomposers:
            raise ValueError(
                f"No decomposer registered for kind={kind.value}. "
                f"Registered: {list(k.value for k in self.decomposers)}"
            )
        return self.decomposers[kind]

    def _compute_context_fit(self, unit: WorkUnit) -> float:
        """Compute context_fit confidence based on estimated token count.

        Returns 1.0 if within budget, scales down as context grows.
        Returns 0.0 if context exceeds the budget — forces decomposition.
        """
        decomposer = self._get_decomposer(unit.kind)
        tokens = decomposer.estimate_context_tokens(unit)
        unit.context_tokens = tokens

        if tokens <= self.context_budget_tokens:
            return 1.0
        else:
            # Linear decay: at 2x budget → 0.0
            ratio = tokens / self.context_budget_tokens
            return max(0.0, 2.0 - ratio)

    async def _evaluate(self, unit: WorkUnit) -> ConfidenceScore:
        """Evaluate a work unit's confidence across all dimensions."""
        unit.status = WorkUnitStatus.EVALUATING
        decomposer = self._get_decomposer(unit.kind)

        # Get kind-specific confidence (implementation + verification)
        score = await decomposer.evaluate(unit, self.tree)

        # Override context_fit with engine's computation
        score.context_fit = self._compute_context_fit(unit)

        unit.confidence = score

        self._log(
            "evaluate",
            unit.id,
            kind=unit.kind.value,
            confidence=score.to_dict(),
        )
        return score

    async def _decompose(self, unit: WorkUnit) -> list[WorkUnit]:
        """Decompose a work unit into children."""
        unit.status = WorkUnitStatus.DECOMPOSING
        decomposer = self._get_decomposer(unit.kind)

        children = await decomposer.decompose(unit, self.tree)

        # Set parent/depth on children
        for child in children:
            child.parent_id = unit.id
            child.depth = unit.depth + 1
            child.max_depth = unit.max_depth

        # Register children in tree
        for child in children:
            self.tree[child.id] = child
            unit.children.append(child.id)

        self._log(
            "decompose",
            unit.id,
            kind=unit.kind.value,
            weakest=unit.confidence.weakest_dimension,
            children=[c.id for c in children],
            children_kinds=[c.kind.value for c in children],
        )

        return children

    async def _execute(self, unit: WorkUnit) -> dict[str, Any]:
        """Execute a work unit that's above threshold."""
        unit.status = WorkUnitStatus.EXECUTING
        decomposer = self._get_decomposer(unit.kind)

        result = await decomposer.execute(unit, self.tree)
        unit.result = result
        unit.status = WorkUnitStatus.DONE

        self._log(
            "execute",
            unit.id,
            kind=unit.kind.value,
            confidence=unit.confidence.overall,
            result_keys=list(result.keys()) if isinstance(result, dict) else [],
        )

        return result

    async def process(self, unit: WorkUnit) -> None:
        """Process a single work unit with convergence detection.

        Enhanced algorithm:
        1. Evaluate confidence
        2. If above threshold → execute
        3. Track confidence history; if Δ < 0.05 for 2 consecutive
           evaluations → converged, execute at current confidence
        4. If below threshold and not converged → decompose → process children
        5. After children complete, re-evaluate parent (enables convergence loop)
        6. Safety: max depth and max total units still enforced as hard limits
        """
        prev_scores: list[float] = []

        while True:
            # Safety: total unit limit
            if len(self.tree) >= self.max_total_units:
                print(f"  ⚠️  Max work units ({self.max_total_units}) reached — "
                      f"executing {unit.id} as-is")
                await self._execute(unit)
                return

            # Step 1: Evaluate
            score = await self._evaluate(unit)

            # Step 2: Check threshold — confident enough to execute
            if score.overall >= self.threshold:
                _print_unit_status(unit, "✓", "executing (confident)")
                await self._execute(unit)
                return

            # Step 3: Convergence check — has confidence stopped improving?
            prev_scores.append(score.overall)
            if len(prev_scores) >= 3:
                # Check last 2 deltas
                deltas = [
                    prev_scores[i] - prev_scores[i - 1]
                    for i in range(len(prev_scores) - 2, len(prev_scores))
                ]
                if all(abs(d) < 0.05 for d in deltas):
                    _print_unit_status(
                        unit, "≈",
                        f"converged (conf={score.overall:.2f}, "
                        f"Δ={deltas[-1]:+.3f})",
                    )
                    await self._execute(unit)
                    return

            # Step 4: Check depth limit (hard safety)
            if unit.depth >= unit.max_depth:
                _print_unit_status(
                    unit, "⚠",
                    f"executing at max depth (conf={score.overall:.2f}, "
                    f"weakest={score.weakest_dimension})",
                )
                await self._execute(unit)
                return

            # Step 5: Decompose
            _print_unit_status(
                unit, "↓",
                f"decomposing (conf={score.overall:.2f}, "
                f"weakest={score.weakest_dimension})",
            )
            children = await self._decompose(unit)

            if not children:
                # Decomposer returned nothing. This can mean:
                # a) Decomposer handled it internally (e.g., generated contracts)
                #    → re-evaluate to check if confidence improved
                # b) Decomposition genuinely impossible → execute as-is
                new_score = await self._evaluate(unit)
                if new_score.overall > score.overall + 0.01:
                    # Internal work improved confidence — continue loop
                    _print_unit_status(
                        unit, "↻",
                        f"internal improvement ({score.overall:.2f} → "
                        f"{new_score.overall:.2f})",
                    )
                    prev_scores.append(new_score.overall)
                    continue
                else:
                    _print_unit_status(
                        unit, "⚠",
                        "no decomposition possible — executing as-is",
                    )
                    await self._execute(unit)
                    return

            # Step 6: Process children recursively
            for child in children:
                await self.process(child)

            # Step 7: After children complete, loop back to re-evaluate parent.
            # This enables convergence detection: if children improved the
            # parent's confidence enough, we execute. If not, the convergence
            # check will eventually trigger.
            # Reset status so re-evaluation can proceed.
            if unit.status == WorkUnitStatus.DECOMPOSING:
                unit.status = WorkUnitStatus.PENDING
            # Continue the while loop → re-evaluate

    async def run(self, initial_units: list[WorkUnit]) -> dict[str, WorkUnit]:
        """Run the engine on a set of initial work units.

        Args:
            initial_units: Starting work units (e.g., from spec parsing)

        Returns:
            The complete work unit tree (id → WorkUnit)
        """
        self._start_time = time.time()
        self.tree.clear()
        self.history.clear()

        # Start telemetry run
        if self.telemetry:
            self.telemetry.start_run()

        # Register initial units
        for unit in initial_units:
            self.tree[unit.id] = unit

        # ─── Pre-run DAG validation (from C's tree validation) ──────
        # Validate the initial task dependencies before starting
        initial_tasks = [
            u.content for u in initial_units
            if u.kind == WorkUnitKind.TASK and isinstance(u.content, dict)
        ]
        if initial_tasks:
            dep_result = validate_task_dependencies(initial_tasks)
            if not dep_result.valid:
                print(f"\n  ⚠️  DAG validation found errors in initial tasks:")
                for err in dep_result.errors:
                    print(f"    ✗ {err}")
                self.logger.info(
                    f"Initial DAG validation: {dep_result}",
                    event_type=EventType.DECOMPOSITION_STARTED,
                    errors=dep_result.errors,
                )
            else:
                print(f"\n  ✓ Initial DAG valid: {dep_result.stats}")

        self.logger.info(
            f"Decomposition engine started: {len(initial_units)} initial units, "
            f"threshold={self.threshold}, budget={self.context_budget_pct:.0%}",
            event_type=EventType.DECOMPOSITION_STARTED,
            initial_units=len(initial_units),
            threshold=self.threshold,
            context_budget_pct=self.context_budget_pct,
        )

        print(f"\n{'=' * 60}")
        print(f"  DECOMPOSITION ENGINE")
        print(f"{'=' * 60}")
        print(f"  Threshold: {self.threshold}")
        print(f"  Context budget: {self.context_budget_pct:.0%} "
              f"({self.context_budget_tokens:,} tokens)")
        print(f"  Initial units: {len(initial_units)}")
        print(f"  Max depth: {initial_units[0].max_depth if initial_units else 3}")
        print()

        # Process initial units concurrently (bounded by max_concurrent)
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _bounded_process(u: WorkUnit) -> None:
            async with semaphore:
                await self.process(u)

        await asyncio.gather(*[_bounded_process(u) for u in initial_units])

        # Summary
        elapsed = time.time() - self._start_time
        done = sum(1 for u in self.tree.values() if u.status == WorkUnitStatus.DONE)
        failed = sum(1 for u in self.tree.values() if u.status == WorkUnitStatus.FAILED)
        total = len(self.tree)
        max_depth = max((u.depth for u in self.tree.values()), default=0)

        self.logger.info(
            f"Decomposition engine complete: {total} units "
            f"({done} done, {failed} failed) in {elapsed:.1f}s",
            event_type=EventType.DECOMPOSITION_COMPLETED,
            total_units=total,
            done=done,
            failed=failed,
            elapsed_s=round(elapsed, 1),
            max_depth=max_depth,
        )

        # ─── Post-run DAG validation ───────────────────────────────
        dag_result = validate_work_unit_dag(self.tree)
        if not dag_result.valid:
            self.logger.info(
                f"Post-run DAG validation failed: {dag_result}",
                event_type=EventType.DECOMPOSITION_COMPLETED,
                errors=dag_result.errors,
            )

        print(f"\n{'=' * 60}")
        print(f"  ENGINE COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Total units: {total} ({done} done, {failed} failed)")
        print(f"  Elapsed: {elapsed:.1f}s")
        print(f"  Decomposition depth: max {max_depth}")
        if dag_result.valid:
            print(f"  DAG validation: ✓ {dag_result.stats}")
        else:
            print(f"  DAG validation: ✗ {len(dag_result.errors)} errors")
            for err in dag_result.errors[:3]:
                print(f"    ✗ {err}")
        if dag_result.warnings:
            for warn in dag_result.warnings[:3]:
                print(f"    ⚠ {warn}")
        print()

        # Persist history and end telemetry
        if self.output_dir:
            self._save_history()
        if self.telemetry:
            self.telemetry.end_run()

        return self.tree

    def _save_history(self) -> None:
        """Save decomposition history and tree to disk."""
        if not self.output_dir:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save history log
        history_path = self.output_dir / "decomposition_history.json"
        history_path.write_text(json.dumps(self.history, indent=2, default=str))

        # Save tree
        tree_path = self.output_dir / "decomposition_tree.json"
        tree_data = {
            uid: unit.to_dict() for uid, unit in self.tree.items()
        }
        tree_path.write_text(json.dumps(tree_data, indent=2, default=str))

    def get_results_by_kind(self, kind: WorkUnitKind) -> list[WorkUnit]:
        """Get all completed work units of a specific kind."""
        return [
            u for u in self.tree.values()
            if u.kind == kind and u.status == WorkUnitStatus.DONE
        ]

    def get_children(self, unit_id: str) -> list[WorkUnit]:
        """Get the children of a work unit."""
        unit = self.tree.get(unit_id)
        if not unit:
            return []
        return [self.tree[cid] for cid in unit.children if cid in self.tree]

    def print_tree(self, root_id: Optional[str] = None, indent: int = 0) -> None:
        """Print the decomposition tree for debugging."""
        if root_id:
            roots = [self.tree[root_id]] if root_id in self.tree else []
        else:
            roots = [u for u in self.tree.values() if u.parent_id is None]

        for unit in roots:
            prefix = "  " * indent
            conf = unit.confidence.overall
            status_icon = {
                WorkUnitStatus.DONE: "✓",
                WorkUnitStatus.FAILED: "✗",
                WorkUnitStatus.EXECUTING: "⟳",
                WorkUnitStatus.DECOMPOSING: "↓",
            }.get(unit.status, "·")

            print(
                f"{prefix}{status_icon} {unit.id} [{unit.kind.value}] "
                f"conf={conf:.2f} {unit.content.get('title', '')[:50]}"
            )

            for child_id in unit.children:
                self.print_tree(child_id, indent + 1)


def _print_unit_status(unit: WorkUnit, icon: str, message: str) -> None:
    """Print a status line for a work unit."""
    indent = "  " * (unit.depth + 1)
    kind = unit.kind.value[:4]
    title = unit.content.get("title", unit.content.get("query", unit.id))
    if len(title) > 50:
        title = title[:47] + "..."
    print(f"{indent}{icon} [{kind}] {title}: {message}")
