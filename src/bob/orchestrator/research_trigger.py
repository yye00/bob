"""Auto-trigger research harness per round for `bob plan`.

Exposes fire_research_for_round(), which runs all six research agents
(R1-R6) in parallel, writes proposals to docs/recursion/round<N>/research/,
and returns a short summary dict suitable for displaying to the user.
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from bob.research.harness import run_all_research_agents
from bob.research.proposal import Proposal


def _summarize(results: dict[str, list[Proposal]]) -> dict[str, Any]:
    """Build a human-readable summary from a full results dict."""
    agent_counts: dict[str, int] = {}
    total = 0
    high_impact: list[str] = []

    for agent_name, proposals in results.items():
        count = len(proposals)
        agent_counts[agent_name] = count
        total += count
        for p in proposals:
            if getattr(p, "estimated_impact", "") == "high":
                high_impact.append(p.title)

    return {
        "total_proposals": total,
        "agent_counts": agent_counts,
        "high_impact_proposals": high_impact,
    }


def fire_research_for_round(
    round_num: int,
    workspace: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Run all six research agents for *round_num* and return a summary.

    Agents execute in parallel via asyncio.gather.  Output YAML files are
    written to docs/recursion/round<N>/research/ (relative to *workspace*,
    or the current working directory when *workspace* is None).

    Args:
        round_num: The planning round index (>= 1).
        workspace: Project root; defaults to pathlib.Path(".").

    Returns:
        A dict with keys:
          - ``round_num``: int — the round that was processed.
          - ``output_dir``: str — path where YAML files were written.
          - ``total_proposals``: int — proposals produced across all agents.
          - ``agent_counts``: dict[str, int] — proposals per agent.
          - ``high_impact_proposals``: list[str] — titles of high-impact proposals.
    """
    if workspace is None:
        workspace = pathlib.Path(".").resolve()
    else:
        workspace = workspace.resolve()

    output_dir = workspace / "docs" / "recursion" / f"round{round_num}" / "research"

    results = asyncio.run(run_all_research_agents(round_num=round_num, output_dir=output_dir))

    summary = _summarize(results)
    summary["round_num"] = round_num
    summary["output_dir"] = str(output_dir)
    return summary
