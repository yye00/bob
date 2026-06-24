"""R6: Self-critique agent — reviews recent decisions and proposes improvements to the build process."""

from __future__ import annotations

import pathlib

from bob3.research.proposal import Proposal


def run(round_num: int) -> list[Proposal]:
    """Return proposals for improving the build/research process itself."""
    proposals: list[Proposal] = []

    research_dir = pathlib.Path("docs") / "recursion" / f"round{round_num}" / "research"
    if research_dir.exists():
        yaml_files = list(research_dir.glob("*.yaml")) + list(research_dir.glob("*.yml"))
        if not yaml_files:
            proposals.append(
                Proposal(
                    domain="self_critique",
                    title="Ensure research outputs are persisted as YAML",
                    rationale=f"Round {round_num} research directory exists but contains no YAML proposal files.",
                    acceptance_criteria=[
                        f"docs/recursion/round{round_num}/research/ contains at least one .yaml file"
                    ],
                    estimated_effort="trivial",
                    estimated_impact="medium",
                    evidence=[f"research_dir={research_dir} exists but is empty of YAML"],
                )
            )

    if round_num > 1:
        prev_research = pathlib.Path("docs") / "recursion" / f"round{round_num - 1}" / "research"
        if not prev_research.exists():
            proposals.append(
                Proposal(
                    domain="self_critique",
                    title=f"Retroactively write round {round_num - 1} research outputs",
                    rationale=f"Round {round_num - 1} research directory missing; prior proposals are untracked.",
                    acceptance_criteria=[f"docs/recursion/round{round_num - 1}/research/ exists"],
                    estimated_effort="small",
                    estimated_impact="low",
                    evidence=[f"prev_research_dir={prev_research} not found"],
                )
            )

    proposals.append(
        Proposal(
            domain="self_critique",
            title=f"Review round {round_num} agent output quality",
            rationale=(
                f"After round {round_num}, each R1-R6 agent's proposals should be reviewed for "
                "relevance, actionability, and effort accuracy before feeding into the next planning cycle."
            ),
            acceptance_criteria=[
                f"All round {round_num} proposals reviewed and tagged as accepted/deferred/rejected",
            ],
            estimated_effort="small",
            estimated_impact="medium",
            evidence=[f"Self-critique triggered for round {round_num}"],
        )
    )

    return proposals
