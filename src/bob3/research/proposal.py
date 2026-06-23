"""Proposal dataclass matching the MASTER_PLAN Phase-4 YAML schema."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Proposal:
    """A research proposal serializable to YAML per MASTER_PLAN Phase-4."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: str = ""
    title: str = ""
    rationale: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    estimated_effort: str = "medium"
    estimated_impact: str = "medium"
    blocked_by: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "title": self.title,
            "rationale": self.rationale,
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_effort": self.estimated_effort,
            "estimated_impact": self.estimated_impact,
            "blocked_by": self.blocked_by,
            "evidence": self.evidence,
        }
