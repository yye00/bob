"""R2: Stack agent — identifies outdated or missing dependencies."""

from __future__ import annotations

import pathlib
import tomllib

from bob.research.proposal import Proposal


def run(round_num: int) -> list[Proposal]:
    """Return proposals for dependency and stack improvements."""
    proposals: list[Proposal] = []

    pyproject = pathlib.Path("pyproject.toml")
    if not pyproject.exists():
        proposals.append(
            Proposal(
                domain="stack",
                title="Add pyproject.toml",
                rationale="No pyproject.toml found; project lacks modern packaging metadata.",
                acceptance_criteria=["pyproject.toml exists and is valid TOML"],
                estimated_effort="small",
                estimated_impact="medium",
                evidence=["pyproject.toml not found in workspace root"],
            )
        )
        return proposals

    with open(pyproject, "rb") as f:
        config = tomllib.load(f)

    deps = config.get("project", {}).get("dependencies", [])
    unpinned = [d for d in deps if ">=" not in d and "==" not in d and "~=" not in d]
    if unpinned:
        proposals.append(
            Proposal(
                domain="stack",
                title="Pin or bound unpinned dependencies",
                rationale=f"{len(unpinned)} dependencies lack version constraints, risking breakage on upgrade.",
                acceptance_criteria=["All dependencies in pyproject.toml have version specifiers"],
                estimated_effort="small",
                estimated_impact="medium",
                evidence=[f"Unpinned: {', '.join(unpinned[:5])}"],
            )
        )

    python_req = config.get("project", {}).get("requires-python", "")
    if not python_req:
        proposals.append(
            Proposal(
                domain="stack",
                title="Add requires-python constraint",
                rationale="No Python version constraint set; the project may silently break on older interpreters.",
                acceptance_criteria=["pyproject.toml includes requires-python"],
                estimated_effort="trivial",
                estimated_impact="low",
                evidence=["requires-python field missing from pyproject.toml"],
            )
        )

    return proposals
