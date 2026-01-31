"""
Work Unit — The universal unit of work in BOB's decomposition engine.
=====================================================================

Every piece of work (task, verification, research) is a WorkUnit with
a confidence score. If confidence is below threshold, decompose it.
Same pattern, applied recursively to everything.

WorkUnit kinds:
- "task"         — A coding task to implement
- "verification" — Verification test generation for a task
- "research"     — A research query (paper, web, computation)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class WorkUnitKind(str, Enum):
    """Types of work units in the decomposition tree."""
    TASK = "task"
    VERIFICATION = "verification"
    RESEARCH = "research"


class WorkUnitStatus(str, Enum):
    """Lifecycle status of a work unit."""
    PENDING = "pending"           # Not yet processed
    EVALUATING = "evaluating"     # Confidence being assessed
    DECOMPOSING = "decomposing"   # Being broken into children
    EXECUTING = "executing"       # Being executed (above threshold)
    DONE = "done"                 # Successfully completed
    FAILED = "failed"             # Failed after all attempts


@dataclass
class ConfidenceScore:
    """Multi-dimensional confidence assessment.

    Each dimension is scored 0.0-1.0. The overall confidence
    is the minimum across all dimensions — the system is only
    as confident as its weakest dimension.
    """
    implementation: float = 0.0   # Can an agent build this atomically?
    verification: float = 0.0     # Will tests catch fakes?
    context_fit: float = 1.0      # Does it fit in 40% of context?
    reason: str = ""              # Human-readable explanation

    @property
    def overall(self) -> float:
        """Overall confidence = minimum across all dimensions."""
        return min(self.implementation, self.verification, self.context_fit)

    @property
    def weakest_dimension(self) -> str:
        """Which dimension is dragging confidence down?"""
        scores = {
            "implementation": self.implementation,
            "verification": self.verification,
            "context_fit": self.context_fit,
        }
        return min(scores, key=scores.get)

    def to_dict(self) -> dict:
        return {
            "implementation": self.implementation,
            "verification": self.verification,
            "context_fit": self.context_fit,
            "overall": self.overall,
            "weakest": self.weakest_dimension,
            "reason": self.reason,
        }


@dataclass
class WorkUnit:
    """Universal unit of work in the decomposition engine.

    Everything is a WorkUnit: tasks, verification generation, research.
    If confidence is below threshold, the unit gets decomposed into
    children. Same pattern at every level.

    Attributes:
        id: Unique identifier
        kind: Type of work (task, verification, research)
        content: Kind-specific payload (task description, query, etc.)
        confidence: Multi-dimensional confidence assessment
        parent_id: ID of parent work unit (for decomposition tracking)
        depth: Current recursion depth
        max_depth: Maximum allowed recursion depth
        status: Lifecycle status
        children: IDs of child work units (after decomposition)
        result: Output from execution (kind-specific)
        context_tokens: Estimated token count for this unit's context
        created_at: When this unit was created
    """
    id: str = field(default_factory=lambda: f"wu-{uuid.uuid4().hex[:8]}")
    kind: WorkUnitKind = WorkUnitKind.TASK
    content: dict[str, Any] = field(default_factory=dict)
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    parent_id: Optional[str] = None
    depth: int = 0
    max_depth: int = 3
    status: WorkUnitStatus = WorkUnitStatus.PENDING
    children: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    context_tokens: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self, include_content: bool = False) -> dict:
        """Serialize for logging and persistence.

        Args:
            include_content: If True, include full content and result dicts.
                             Default False to keep tree dumps small.
        """
        d = {
            "id": self.id,
            "kind": self.kind.value,
            "content_keys": list(self.content.keys()),
            "confidence": self.confidence.to_dict(),
            "parent_id": self.parent_id,
            "depth": self.depth,
            "max_depth": self.max_depth,
            "status": self.status.value,
            "children": self.children,
            "context_tokens": self.context_tokens,
        }
        if include_content:
            d["content"] = self.content
            d["result"] = self.result
        else:
            # Always include result summary for debugging
            if isinstance(self.result, dict):
                d["result_keys"] = list(self.result.keys())
                # For verification units, include test counts
                for cat in ("numerical_tests", "algorithmic_tests", "convergence_tests"):
                    if cat in self.result:
                        d[f"result_{cat}_count"] = len(self.result[cat])
            elif self.result is not None:
                d["result_type"] = type(self.result).__name__
        return d

    def __repr__(self) -> str:
        return (
            f"WorkUnit(id={self.id!r}, kind={self.kind.value}, "
            f"conf={self.confidence.overall:.2f}, depth={self.depth}, "
            f"status={self.status.value})"
        )
