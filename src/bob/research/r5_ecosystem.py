"""R5: Ecosystem agent — identifies integration and ecosystem improvement opportunities."""

from __future__ import annotations

import pathlib

from bob.research.proposal import Proposal


def run(round_num: int) -> list[Proposal]:
    """Return proposals for ecosystem and tooling improvements."""
    proposals: list[Proposal] = []

    workspace = pathlib.Path(".")

    if not (workspace / ".github" / "workflows").exists():
        proposals.append(
            Proposal(
                domain="ecosystem",
                title="Add CI workflow (GitHub Actions)",
                rationale="No CI configuration found; untested changes can merge without validation.",
                acceptance_criteria=[
                    ".github/workflows/ci.yml exists",
                    "Workflow runs pytest on push and PR",
                ],
                estimated_effort="small",
                estimated_impact="high",
                evidence=["No .github/workflows/ directory found"],
            )
        )

    if not (workspace / "Makefile").exists() and not (workspace / "justfile").exists():
        proposals.append(
            Proposal(
                domain="ecosystem",
                title="Add developer task runner (Makefile or justfile)",
                rationale="No task runner found; common commands (test, lint, format) should be documented and reproducible.",
                acceptance_criteria=["Makefile or justfile exists with test, lint, format targets"],
                estimated_effort="small",
                estimated_impact="low",
                evidence=["No Makefile or justfile found in workspace root"],
            )
        )

    if not (workspace / "CHANGELOG.md").exists() and not (workspace / "CHANGES.md").exists():
        proposals.append(
            Proposal(
                domain="ecosystem",
                title="Add CHANGELOG",
                rationale="No changelog found; release history is not captured for users.",
                acceptance_criteria=["CHANGELOG.md exists with at least one version entry"],
                estimated_effort="trivial",
                estimated_impact="low",
                evidence=["No CHANGELOG.md or CHANGES.md found"],
            )
        )

    ruff_configured = False
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8", errors="replace")
        ruff_configured = "[tool.ruff]" in content

    if not ruff_configured and not (workspace / ".ruff.toml").exists():
        proposals.append(
            Proposal(
                domain="ecosystem",
                title="Configure ruff linter",
                rationale="No ruff configuration found; code style enforcement is absent.",
                acceptance_criteria=["[tool.ruff] section exists in pyproject.toml", "ruff check src/ exits with 0"],
                estimated_effort="small",
                estimated_impact="medium",
                evidence=["No ruff configuration detected"],
            )
        )

    return proposals
