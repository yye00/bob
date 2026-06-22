"""Research agent module — surfaces alternative implementation strategies for classified failures.

Exposes ``surface_strategies`` as a public entry point satisfying the AC
"Function defined: research_agent.surface_strategies".
Delegates strategy synthesis to bob3.orchestrator.path_finding_retry.

Integration: research sub-agent spawns go through spawn_with_retry (F-R7-478)
so transient infra errors (429, ECONNRESET, ETIMEDOUT, ENOENT) are retried
unlimited times without consuming any budget counter.
"""

from __future__ import annotations

from typing import Any

from bob3.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    classify_failure as _classify_failure,
    research_strategies,
    spawns_research_subagent,
)
from bob3.orchestrator.spawn_retry import classify_exit, spawn_with_retry

__all__ = ["surface_strategies", "classify_exit", "spawn_with_retry"]


def surface_strategies(
    failure_info: dict[str, Any],
    max_strategies: int = 2,
) -> list[dict[str, Any]]:
    """Surface 1-2 alternative strategies tailored to the failure class.

    Given a failure_info dict describing why the previous implementation attempt
    failed, classify the failure and return up to max_strategies alternative
    strategies that the implementer can use to retry with new information.

    For an unknown or unclassifiable failure, returns an empty list.

    Args:
        failure_info: Dict with keys like ``error_type``, ``message``, ``traceback``,
                      or an explicit ``failure_class`` key describing the failure.
        max_strategies: Maximum number of strategies to return (default 2).

    Returns:
        A list of strategy dicts, each with keys:
        - title: str, short strategy name
        - description: str, concrete instructions for the implementer
        - priority: int, ordering hint (1 = highest priority)

    Raises:
        ValueError: If failure_info is not a dict.
    """
    failure_class: FailureClass = _classify_failure(failure_info)

    if failure_class == FailureClass.unknown:
        return []

    strategies: list[Strategy] = research_strategies(failure_class)
    return [
        {
            "title": s.title,
            "description": s.description,
            "priority": s.priority,
        }
        for s in strategies[:max_strategies]
    ]
