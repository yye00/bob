"""Research-and-Expand harness: runs R1..R7 agents in parallel and writes proposals to disk."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

import yaml

from bob3.research import (
    r1_coverage,
    r2_stack,
    r3_perf,
    r4_security,
    r5_ecosystem,
    r6_self_critique,
    r7_literature,
)
from bob3.research.proposal import Proposal

_AGENTS = [
    r1_coverage,
    r2_stack,
    r3_perf,
    r4_security,
    r5_ecosystem,
    r6_self_critique,
    r7_literature,
]


def _run_agent_sync(agent: Any, round_num: int) -> list[Proposal]:
    """Run a single synchronous agent, catching any errors."""
    try:
        return agent.run(round_num)
    except Exception as exc:  # noqa: BLE001
        return [
            Proposal(
                domain="error",
                title=f"Agent {agent.__name__} failed",
                rationale=str(exc),
                evidence=[f"Exception: {type(exc).__name__}: {exc}"],
            )
        ]


async def _run_agent_async(agent: Any, round_num: int) -> list[Proposal]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_agent_sync, agent, round_num)


async def run_all_research_agents(
    round_num: int,
    output_dir: pathlib.Path | None = None,
) -> dict[str, list[Proposal]]:
    """Run all six research agents in parallel and write results to disk.

    Args:
        round_num: The current research round number (used for output path).
        output_dir: Override the output directory. Defaults to
            docs/recursion/round<N>/research/ relative to cwd.

    Returns:
        Mapping of agent module name to its list of Proposal objects.
    """
    if output_dir is None:
        output_dir = pathlib.Path("docs") / "recursion" / f"round{round_num}" / "research"

    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = [_run_agent_async(agent, round_num) for agent in _AGENTS]
    results_list: list[list[Proposal]] = await asyncio.gather(*tasks)

    results: dict[str, list[Proposal]] = {}
    for agent, proposals in zip(_AGENTS, results_list):
        agent_name = agent.__name__.split(".")[-1]
        results[agent_name] = proposals

        out_file = output_dir / f"{agent_name}.yaml"
        serialized = [p.to_dict() for p in proposals]
        out_file.write_text(yaml.dump(serialized, default_flow_style=False, sort_keys=False), encoding="utf-8")

    return results
