"""
Tests for the recursive decomposition engine.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from bob.orchestrator.work_unit import (
    WorkUnit,
    WorkUnitKind,
    WorkUnitStatus,
    ConfidenceScore,
)
from bob.orchestrator.decomposer import Decomposer
from bob.orchestrator.decomposition_engine import DecompositionEngine


# ---------------------------------------------------------------------------
# Test fixtures: mock decomposers
# ---------------------------------------------------------------------------

class AlwaysConfidentDecomposer(Decomposer):
    """A decomposer that always evaluates as confident → executes immediately."""

    async def evaluate(self, unit, tree):
        return ConfidenceScore(implementation=0.95, verification=0.95)

    async def decompose(self, unit, tree):
        return []  # Should never be called

    async def execute(self, unit, tree):
        return {"status": "executed"}


class NeverConfidentDecomposer(Decomposer):
    """A decomposer that's never confident → always decomposes.

    Decomposes into 2 children (of a different kind that IS confident),
    preventing infinite recursion.
    """

    def __init__(self):
        self.decompose_count = 0

    async def evaluate(self, unit, tree):
        return ConfidenceScore(implementation=0.3, verification=0.3,
                               reason="always low")

    async def decompose(self, unit, tree):
        self.decompose_count += 1
        # Return children of kind RESEARCH (which will be confident)
        return [
            WorkUnit(
                kind=WorkUnitKind.RESEARCH,
                content={"query": f"child-{i}", "title": f"Child {i}"},
            )
            for i in range(2)
        ]

    async def execute(self, unit, tree):
        return {"status": "forced-execute"}


class ContextHungryDecomposer(Decomposer):
    """A decomposer whose work units are too large for context."""

    async def evaluate(self, unit, tree):
        return ConfidenceScore(implementation=0.95, verification=0.95)

    async def decompose(self, unit, tree):
        # Split into 2 smaller units
        return [
            WorkUnit(
                kind=WorkUnitKind.TASK,
                content={"title": "smaller-1", "description": "x" * 1000},
            ),
            WorkUnit(
                kind=WorkUnitKind.TASK,
                content={"title": "smaller-2", "description": "x" * 1000},
            ),
        ]

    async def execute(self, unit, tree):
        return {"status": "executed"}

    def estimate_context_tokens(self, unit):
        # Return a huge number to trigger context_fit decomposition
        return 500_000  # Way over 40% of 200K


# ---------------------------------------------------------------------------
# Tests: WorkUnit
# ---------------------------------------------------------------------------

class TestWorkUnit:
    def test_creation(self):
        unit = WorkUnit(
            kind=WorkUnitKind.TASK,
            content={"title": "Test Task", "description": "Do something"},
        )
        assert unit.kind == WorkUnitKind.TASK
        assert unit.status == WorkUnitStatus.PENDING
        assert unit.depth == 0
        assert unit.confidence.overall == 0.0

    def test_confidence_score(self):
        score = ConfidenceScore(
            implementation=0.9,
            verification=0.5,
            context_fit=1.0,
        )
        assert score.overall == 0.5  # min across dimensions
        assert score.weakest_dimension == "verification"

    def test_confidence_all_equal(self):
        score = ConfidenceScore(
            implementation=0.8,
            verification=0.8,
            context_fit=0.8,
        )
        assert score.overall == 0.8

    def test_context_fit_weakest(self):
        score = ConfidenceScore(
            implementation=0.95,
            verification=0.95,
            context_fit=0.3,
        )
        assert score.weakest_dimension == "context_fit"
        assert score.overall == 0.3

    def test_to_dict(self):
        unit = WorkUnit(
            kind=WorkUnitKind.VERIFICATION,
            content={"task_id": "D003"},
        )
        d = unit.to_dict()
        assert d["kind"] == "verification"
        assert "task_id" in d["content_keys"]


# ---------------------------------------------------------------------------
# Tests: DecompositionEngine
# ---------------------------------------------------------------------------

class TestDecompositionEngine:
    def test_register_decomposer(self):
        engine = DecompositionEngine()
        decomposer = AlwaysConfidentDecomposer()
        engine.register(WorkUnitKind.TASK, decomposer)
        assert WorkUnitKind.TASK in engine.decomposers

    def test_missing_decomposer_raises(self):
        engine = DecompositionEngine()
        unit = WorkUnit(kind=WorkUnitKind.TASK, content={})
        with pytest.raises(ValueError, match="No decomposer registered"):
            engine._get_decomposer(WorkUnitKind.TASK)

    @pytest.mark.asyncio
    async def test_confident_unit_executes_directly(self):
        engine = DecompositionEngine(threshold=0.9)
        engine.register(WorkUnitKind.TASK, AlwaysConfidentDecomposer())

        unit = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Test"})
        engine.tree[unit.id] = unit
        await engine.process(unit)

        assert unit.status == WorkUnitStatus.DONE
        assert unit.result == {"status": "executed"}
        assert len(unit.children) == 0

    @pytest.mark.asyncio
    async def test_low_confidence_decomposes(self):
        engine = DecompositionEngine(threshold=0.9)
        low_decomposer = NeverConfidentDecomposer()
        engine.register(WorkUnitKind.TASK, low_decomposer)
        engine.register(WorkUnitKind.RESEARCH, AlwaysConfidentDecomposer())

        unit = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Hard"})
        engine.tree[unit.id] = unit
        await engine.process(unit)

        # Should have decomposed
        assert low_decomposer.decompose_count == 1
        assert len(unit.children) == 2

        # Children should be executed
        for child_id in unit.children:
            child = engine.tree[child_id]
            assert child.status == WorkUnitStatus.DONE
            assert child.kind == WorkUnitKind.RESEARCH

    @pytest.mark.asyncio
    async def test_max_depth_forces_execution(self):
        engine = DecompositionEngine(threshold=0.9)
        low_decomposer = NeverConfidentDecomposer()
        engine.register(WorkUnitKind.TASK, low_decomposer)
        engine.register(WorkUnitKind.RESEARCH, AlwaysConfidentDecomposer())

        unit = WorkUnit(
            kind=WorkUnitKind.TASK,
            content={"title": "Deep"},
            depth=3,  # Already at max
            max_depth=3,
        )
        engine.tree[unit.id] = unit
        await engine.process(unit)

        # Should NOT decompose — at max depth
        assert low_decomposer.decompose_count == 0
        assert unit.status == WorkUnitStatus.DONE
        assert unit.result == {"status": "forced-execute"}

    @pytest.mark.asyncio
    async def test_context_budget_forces_decomposition(self):
        engine = DecompositionEngine(
            threshold=0.9,
            context_budget_pct=0.4,
            context_window_tokens=200_000,
        )
        hungry = ContextHungryDecomposer()
        # Register for both TASK (hungry) — but children will also be TASK
        # so we need to make the children use a different (small) estimator
        confident = AlwaysConfidentDecomposer()
        engine.register(WorkUnitKind.TASK, hungry)

        unit = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Huge"})
        engine.tree[unit.id] = unit

        # The engine will evaluate → context_fit will be low → decompose
        score = await engine._evaluate(unit)
        assert score.context_fit < 0.9  # Should be low due to 500K tokens

    @pytest.mark.asyncio
    async def test_run_multiple_units(self):
        engine = DecompositionEngine(threshold=0.9)
        engine.register(WorkUnitKind.TASK, AlwaysConfidentDecomposer())

        units = [
            WorkUnit(kind=WorkUnitKind.TASK, content={"title": f"Task {i}"})
            for i in range(3)
        ]

        tree = await engine.run(units)

        assert len(tree) == 3
        for unit in tree.values():
            assert unit.status == WorkUnitStatus.DONE

    @pytest.mark.asyncio
    async def test_max_units_safety(self):
        engine = DecompositionEngine(threshold=0.9, max_total_units=5)
        engine.register(WorkUnitKind.TASK, AlwaysConfidentDecomposer())

        units = [
            WorkUnit(kind=WorkUnitKind.TASK, content={"title": f"Task {i}"})
            for i in range(10)
        ]

        tree = await engine.run(units)
        # All 10 should still be processed (max_units is per-process, not initial)
        # But the engine won't create MORE than max_total_units
        assert len(tree) == 10

    @pytest.mark.asyncio
    async def test_history_tracking(self):
        engine = DecompositionEngine(threshold=0.9)
        engine.register(WorkUnitKind.TASK, AlwaysConfidentDecomposer())

        unit = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Test"})
        await engine.run([unit])

        # Should have evaluate + execute entries
        assert len(engine.history) >= 2
        actions = [h["action"] for h in engine.history]
        assert "evaluate" in actions
        assert "execute" in actions

    @pytest.mark.asyncio
    async def test_tree_parent_child_tracking(self):
        engine = DecompositionEngine(threshold=0.9)
        low = NeverConfidentDecomposer()
        engine.register(WorkUnitKind.TASK, low)
        engine.register(WorkUnitKind.RESEARCH, AlwaysConfidentDecomposer())

        root = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Root"})
        await engine.run([root])

        # Check parent-child relationships
        children = engine.get_children(root.id)
        assert len(children) == 2
        for child in children:
            assert child.parent_id == root.id
            assert child.depth == 1

    def test_context_fit_computation(self):
        engine = DecompositionEngine(
            context_budget_pct=0.4,
            context_window_tokens=200_000,
        )
        # Budget = 80,000 tokens
        engine.register(WorkUnitKind.TASK, AlwaysConfidentDecomposer())

        # Unit with small content → context_fit = 1.0
        small = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Small"})
        fit = engine._compute_context_fit(small)
        assert fit == 1.0

    @pytest.mark.asyncio
    async def test_empty_decomposition_falls_through_to_execute(self):
        """If decompose returns [], engine should execute the unit."""

        class EmptyDecomposer(Decomposer):
            async def evaluate(self, unit, tree):
                return ConfidenceScore(implementation=0.5, verification=0.5)

            async def decompose(self, unit, tree):
                return []  # No decomposition possible

            async def execute(self, unit, tree):
                return {"status": "executed-anyway"}

        engine = DecompositionEngine(threshold=0.9)
        engine.register(WorkUnitKind.TASK, EmptyDecomposer())

        unit = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Stuck"})
        await engine.run([unit])

        assert unit.status == WorkUnitStatus.DONE
        assert unit.result == {"status": "executed-anyway"}


    @pytest.mark.asyncio
    async def test_parent_execute_called_after_children_complete(self):
        """After children complete, parent's execute() must be called
        so it can collect child results (e.g., verification tests).
        
        This is the fix for the bug where verification tests were generated
        by child verification units but never merged into the parent task.
        """

        class ParentDecomposer(Decomposer):
            """Decomposes into one child, then execute() collects child results."""

            def __init__(self):
                self.execute_calls = []

            async def evaluate(self, unit, tree):
                return ConfidenceScore(implementation=0.3, verification=0.3)

            async def decompose(self, unit, tree):
                return [
                    WorkUnit(
                        kind=WorkUnitKind.RESEARCH,
                        content={"query": "verify", "title": "Verification"},
                    )
                ]

            async def execute(self, unit, tree):
                self.execute_calls.append(unit.id)
                # Collect child results
                child_results = []
                for child_id in unit.children:
                    child = tree.get(child_id)
                    if child and child.result:
                        child_results.append(child.result)
                return {"status": "collected", "child_results": child_results}

        parent_decomposer = ParentDecomposer()

        engine = DecompositionEngine(threshold=0.9)
        engine.register(WorkUnitKind.TASK, parent_decomposer)
        engine.register(WorkUnitKind.RESEARCH, AlwaysConfidentDecomposer())

        parent = WorkUnit(kind=WorkUnitKind.TASK, content={"title": "Parent"})
        tree = await engine.run([parent])

        # Parent's execute() should have been called
        assert parent.id in parent_decomposer.execute_calls
        # Parent should have result with collected child data
        assert parent.result is not None
        assert parent.result["status"] == "collected"
        assert len(parent.result["child_results"]) == 1
        assert parent.result["child_results"][0] == {"status": "executed"}


# ---------------------------------------------------------------------------
# Tests: Decomposer interface
# ---------------------------------------------------------------------------

class TestDecomposerInterface:
    def test_estimate_context_tokens_default(self):
        """Default implementation uses chars/4 heuristic."""
        decomposer = AlwaysConfidentDecomposer()
        unit = WorkUnit(
            kind=WorkUnitKind.TASK,
            content={"title": "Test", "description": "x" * 4000},
        )
        tokens = decomposer.estimate_context_tokens(unit)
        # Should be roughly 1000+ tokens (4000 chars / 4)
        assert tokens > 500
        assert tokens < 5000
