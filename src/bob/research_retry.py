"""Research-augmented retry — path-finding on ambiguous AC failure.

Exposes public functions used by the orchestration loop:
- classify_failure: classify a failure dict into a string failure class
- spawn_research_subagent: assert that research sub-agent spawning is supported
- spawn_research_agent: alias for spawn_research_subagent
- inject_strategies: inject research strategies into an implementer prompt prefix

When refinement_attempts >= 2 AND the previous attempt's failure is
classifiable, classify the failure, surface 1-2 alternative strategies,
and inject strategies into the next implementer's prompt prefix so the
implementer retries with NEW information.
"""

from __future__ import annotations

from typing import Any

from bob.orchestrator.path_finding_retry import (
    FailureClass,
    classify_failure as _classify_failure,
    inject_into_implementer_prompt,
    research_strategies,
    spawns_research_subagent,
)


def classify_failure(failure_info: dict[str, Any]) -> str:
    """Classify a feature implementation failure into a failure class string.

    Args:
        failure_info: Dict with keys like ``error_type``, ``message``, ``traceback``,
                      or an explicit ``failure_class`` key.

    Returns:
        A string naming the failure class (e.g. ``"import_error"``).

    Raises:
        ValueError: If ``failure_info`` is not a dict or contains an invalid
                    explicit ``failure_class`` value.
    """
    return _classify_failure(failure_info).value


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
    try:
        fc = FailureClass(failure_class_str)
    except (ValueError, TypeError):
        raise ValueError(
            f"spawn_research_agent: {failure_class_str!r} is not a valid failure class; "
            f"valid values are {[fc.value for fc in FailureClass]}"
        )
    return fc != FailureClass.unknown and spawns_research_subagent()


def spawn_research_subagent(failure_class_str: str) -> bool:
    """Return True if a research sub-agent should be spawned for the given failure class.

    Canonical name for the sub-agent spawn gate. ``spawn_research_agent`` is an
    alias for this function; both names are exported for compatibility.

    A research sub-agent is spawned for any classifiable (non-unknown) failure class.
    For ``"unknown"`` failure class, returns False.

    Args:
        failure_class_str: A failure class string (e.g. ``"import_error"``).

    Returns:
        True when a research sub-agent should be spawned; False for ``"unknown"``.

    Raises:
        ValueError: If ``failure_class_str`` is not a valid FailureClass value.
    """
    return spawn_research_agent(failure_class_str)


def inject_strategies(
    base_prompt: str,
    failure_class: str,
    attempt_number: int,
) -> str:
    """Inject research strategies into an implementer prompt prefix.

    For classifiable (non-unknown) failure classes, prepends a structured
    strategies block to the base implementer prompt so the implementer retries
    with new information. For ``"unknown"``, returns the base prompt unchanged.

    Args:
        base_prompt: The original implementer prompt.
        failure_class: A failure class string (e.g. ``"import_error"``).
        attempt_number: The current attempt number (>= 1).

    Returns:
        The (possibly augmented) implementer prompt string.

    Raises:
        ValueError: If ``failure_class`` is not a valid FailureClass value.
    """
    try:
        fc = FailureClass(failure_class)
    except (ValueError, TypeError):
        raise ValueError(
            f"inject_strategies: {failure_class!r} is not a valid failure class; "
            f"valid values are {[fc.value for fc in FailureClass]}"
        )

    if fc == FailureClass.unknown:
        return base_prompt

    strategies = research_strategies(fc)
    return inject_into_implementer_prompt(
        base_prompt=base_prompt,
        strategies=strategies,
        failure_class=fc,
        attempt_number=attempt_number,
    )
