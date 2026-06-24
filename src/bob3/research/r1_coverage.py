"""R1: Coverage agent — identifies gaps in test coverage."""

from __future__ import annotations

import pathlib

from bob3.research.proposal import Proposal


def run(round_num: int) -> list[Proposal]:
    """Return proposals for improving test coverage gaps."""
    workspace = pathlib.Path(".")
    src_files = list((workspace / "src").rglob("*.py")) if (workspace / "src").exists() else []
    test_files = list((workspace / "tests").rglob("test_*.py")) if (workspace / "tests").exists() else []

    proposals: list[Proposal] = []

    if not test_files:
        proposals.append(
            Proposal(
                domain="coverage",
                title="Bootstrap test suite",
                rationale="No test files found; coverage is effectively 0%.",
                acceptance_criteria=["pytest exits with 0"],
                estimated_effort="large",
                estimated_impact="high",
                evidence=["No test_*.py files detected in tests/"],
            )
        )
        return proposals

    src_modules = {f.stem for f in src_files if f.stem != "__init__"}
    tested_modules = set()
    for tf in test_files:
        name = tf.stem.removeprefix("test_")
        tested_modules.add(name)

    untested = sorted(src_modules - tested_modules)
    for module in untested[:5]:
        proposals.append(
            Proposal(
                domain="coverage",
                title=f"Add tests for {module}",
                rationale=f"Module {module} has no corresponding test file.",
                acceptance_criteria=[f"pytest tests/test_{module}.py exits with 0"],
                estimated_effort="small",
                estimated_impact="medium",
                evidence=[f"src module {module} found; no test_{module}.py detected"],
            )
        )

    return proposals
