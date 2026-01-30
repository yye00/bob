"""
Decomposer — Abstract base class for all decomposition strategies.
===================================================================

A Decomposer handles one kind of WorkUnit (task, verification, research).
It can:
1. Evaluate confidence — score how ready the unit is
2. Decompose — break into smaller children if not ready
3. Execute — do the actual work when confident enough

The DecompositionEngine calls these methods in order, recursively,
until everything is above the confidence threshold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bob.orchestrator.work_unit import WorkUnit, ConfidenceScore


class Decomposer(ABC):
    """Base class for all decomposition strategies.

    Implement one per WorkUnit kind. Register in the DecompositionEngine.

    The contract:
    - evaluate() returns a ConfidenceScore (multi-dimensional)
    - decompose() returns a list of child WorkUnits
    - execute() does the work and returns results
    - estimate_context_tokens() returns the estimated token count

    All methods receive the full work unit tree (as a dict of id→unit)
    so they can look up parent/sibling context when needed.
    """

    @abstractmethod
    async def evaluate(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> ConfidenceScore:
        """Assess confidence for a work unit.

        Returns a multi-dimensional score. The engine uses the overall
        (minimum) to decide whether to decompose or execute.

        Args:
            unit: The work unit to evaluate
            tree: All work units in the current decomposition tree

        Returns:
            ConfidenceScore with implementation, verification, context_fit
        """

    @abstractmethod
    async def decompose(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> list[WorkUnit]:
        """Break a work unit into smaller children.

        Called when confidence is below threshold. The decomposition
        strategy depends on which dimension is weakest:
        - implementation low → break task into sub-tasks
        - verification low → generate verification work units
        - context_fit low → split context into smaller pieces

        Args:
            unit: The work unit to decompose
            tree: All work units in the current decomposition tree

        Returns:
            List of child WorkUnits (will be added to the tree)
        """

    @abstractmethod
    async def execute(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> dict[str, Any]:
        """Execute a work unit that's above the confidence threshold.

        What "execute" means depends on the kind:
        - task → send to Claude Code for implementation
        - verification → generate and store tests
        - research → read paper / search web / compute value

        Args:
            unit: The work unit to execute
            tree: All work units in the current decomposition tree

        Returns:
            Result dict (kind-specific)
        """

    def estimate_context_tokens(self, unit: WorkUnit) -> int:
        """Estimate the token count for this unit's full context.

        Used by the engine to compute context_fit confidence.
        Default implementation uses a rough chars/4 heuristic.
        Override for more precise estimation.

        Args:
            unit: The work unit to estimate

        Returns:
            Estimated token count
        """
        # Rough estimate: serialize content to string, divide by 4
        import json
        content_str = json.dumps(unit.content, default=str)
        return len(content_str) // 4
