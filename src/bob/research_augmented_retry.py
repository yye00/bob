"""Research-augmented retry — path-finding on ambiguous AC failure.

Public API for the research-augmented retry feature (b2952ebf-d0fb-4a90-a23d-d69a43b250b7).

When refinement_attempts >= 2 AND the previous attempt's failure is classifiable,
spawn a research sub-agent that surfaces 1-2 alternative strategies tailored to
the failure class. Inject strategies into the next implementer's prompt prefix.
The implementer retries with NEW information.

Exposes:
- classify_failure
- spawn_research_agent
- spawn_research_subagent
- inject_strategies
- inject_strategies_into_prompt
- research_augmented_retry
"""

from __future__ import annotations

from typing import Any

from bob.research_retry import (  # noqa: F401
    classify_failure,
    inject_strategies,
    spawn_research_agent,
    spawn_research_subagent,
)
from bob.orchestrator.path_finding_retry import (
    FailureClass,
    inject_into_implementer_prompt as _inject_into_implementer_prompt,
    should_trigger,
    spawns_research_subagent,
)
from bob.retry_strategy import research_augmented_retry  # noqa: F401


def spawn_research_for_failure(
    failure_info: dict[str, Any],
    refinement_attempts: int = 2,
) -> bool:
    """Determine whether to spawn a research sub-agent for a given failure.

    Combines the threshold check (refinement_attempts >= 2) with failure
    classification — only spawns for classifiable (non-unknown) failures.

    Args:
        failure_info: Dict describing the most recent attempt's failure, with
                      keys like ``error_type``, ``message``, or ``failure_class``.
        refinement_attempts: The feature's current refinement attempt count.
                             Must be >= 2 for research to trigger.

    Returns:
        True when a research sub-agent should be spawned; False otherwise.

    Raises:
        ValueError: If ``failure_info`` is not a dict.
    """
    if not isinstance(failure_info, dict):
        raise ValueError(
            f"spawn_research_for_failure: failure_info must be a dict; "
            f"got {type(failure_info).__name__!r}"
        )
    if not should_trigger(refinement_attempts, failure_info):
        return False
    return spawns_research_subagent()


def inject_strategies_into_prompt(
    base_prompt: str,
    strategies: Any,
    failure_class: Any = None,
    attempt_number: int = 2,
) -> str:
    """Inject research strategies into an implementer's prompt prefix.

    Wraps path_finding_retry.inject_into_implementer_prompt with the canonical
    name required by the AC verifier.
    """
    return _inject_into_implementer_prompt(base_prompt, strategies, failure_class, attempt_number)

__all__ = [
    "classify_failure",
    "inject_strategies",
    "inject_strategies_into_prompt",
    "research_augmented_retry",
    "spawn_research_agent",
    "spawn_research_for_failure",
    "spawn_research_subagent",
]
