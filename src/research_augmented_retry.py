"""Research-augmented retry — path-finding on ambiguous AC failure.

Exposes two public functions required by the ACs:
  - Function defined: research_augmented_retry.spawn_research_agent
  - Function defined: research_augmented_retry.inject_strategies

Delegates to the canonical implementations in bob.retry_strategy and
bob.orchestrator.path_finding_retry.
"""

from __future__ import annotations

from typing import Any

from bob.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    inject_into_implementer_prompt,
    research_strategies,
)
from bob.retry_strategy import spawn_research_agent as _spawn_research_agent

__all__ = [
    "spawn_research_agent",
    "inject_strategies",
]


def spawn_research_agent(failure_class_str: str) -> bool:
    """Return True if a research sub-agent should be spawned for the given failure class.

    A research sub-agent is spawned for any classifiable (non-unknown) failure class.
    For ``"unknown"`` failure class, returns False.

    Args:
        failure_class_str: A failure class string (e.g. ``"import_error"``).

    Returns:
        True when a research sub-agent should be spawned; False for ``"unknown"``.

    Raises:
        ValueError: If ``failure_class_str`` is not a valid FailureClass value.
    """
    return _spawn_research_agent(failure_class_str)


def inject_strategies(
    base_prompt: str,
    failure_class_str: str,
    attempt_number: int,
    max_strategies: int = 2,
) -> str:
    """Inject research strategies into an implementer prompt.

    Classifies the failure, surfaces up to max_strategies alternative strategies,
    and returns a new prompt string with the strategies block prepended.

    Args:
        base_prompt: The original implementer prompt.
        failure_class_str: A failure class string (e.g. ``"import_error"``).
        attempt_number: The current attempt index (>= 1).
        max_strategies: Maximum number of strategies to inject (default 2).

    Returns:
        A new prompt string with strategies prepended, or base_prompt unchanged
        if the failure class is ``"unknown"`` or the failure class string is invalid.

    Raises:
        ValueError: If ``failure_class_str`` is not a valid FailureClass value.
    """
    try:
        fc = FailureClass(failure_class_str)
    except ValueError:
        raise ValueError(
            f"inject_strategies: {failure_class_str!r} is not a valid failure class; "
            f"valid values are {[f.value for f in FailureClass]}"
        )

    if fc == FailureClass.unknown:
        return base_prompt

    strategies: list[Strategy] = research_strategies(fc)[:max_strategies]

    return inject_into_implementer_prompt(
        base_prompt=base_prompt,
        strategies=strategies,
        failure_class=fc,
        attempt_number=attempt_number,
    )
