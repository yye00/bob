"""Research-augmented retry strategy for ambiguous AC failure path-finding.

Exposes three public functions:
- research_augmented_retry: full retry path-finding entry point
- classify_failure: classify a failure dict into a FailureClass
- spawn_research_agent: assert that research sub-agent spawning is supported
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    cache_strategies_per_attempt,
    classify_failure as _classify_failure,
    inject_into_implementer_prompt,
    persist_implementer_prompt,
    research_strategies,
    should_trigger,
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
    except ValueError:
        raise ValueError(
            f"spawn_research_agent: {failure_class_str!r} is not a valid failure class; "
            f"valid values are {[fc.value for fc in FailureClass]}"
        )
    return fc != FailureClass.unknown and spawns_research_subagent()


def research_augmented_retry(
    refinement_attempts: int,
    failure_info: dict[str, Any],
    base_prompt: str,
    feature_id: str,
    attempt_number: int,
    workspace: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Run research-augmented retry path-finding on ambiguous AC failure.

    When refinement_attempts >= 2 AND the previous attempt's failure is
    classifiable, classify the failure, surface 1-2 alternative strategies,
    inject them into the implementer prompt prefix, and persist both
    strategies and prompt to disk.

    Args:
        refinement_attempts: The feature's current refinement attempt count.
        failure_info: Dict describing the most recent attempt's failure.
        base_prompt: The original implementer prompt to inject strategies into.
        feature_id: The feature UUID (used for persistence paths).
        attempt_number: The current attempt index (>= 1, used for persistence).
        workspace: Project root directory; defaults to current working directory.

    Returns:
        A dict with keys:
        - triggered: bool, True iff the retry path-finding fired
        - failure_class: str, the classified failure class value (or "unknown")
        - strategies: list of strategy dicts (title, description, priority)
        - prompt: str, the (possibly augmented) implementer prompt
        - strategies_path: str or None, path where strategies were cached
        - prompt_path: str or None, path where the prompt was persisted

    Raises:
        ValueError: If failure_info is not a dict.
    """
    triggered = should_trigger(refinement_attempts, failure_info)

    fc: FailureClass = _classify_failure(failure_info)
    strategies: list[Strategy] = []
    strategies_path: pathlib.Path | None = None
    prompt_path: pathlib.Path | None = None
    prompt = base_prompt

    if triggered:
        strategies = research_strategies(fc)
        prompt = inject_into_implementer_prompt(
            base_prompt=base_prompt,
            strategies=strategies,
            failure_class=fc,
            attempt_number=attempt_number,
        )
        strategies_path = cache_strategies_per_attempt(
            feature_id=feature_id,
            attempt_number=attempt_number,
            strategies=strategies,
            workspace=workspace,
        )
        prompt_path = persist_implementer_prompt(
            feature_id=feature_id,
            attempt_number=attempt_number,
            prompt=prompt,
            workspace=workspace,
        )

    return {
        "triggered": triggered,
        "failure_class": fc.value,
        "strategies": [
            {
                "title": s.title,
                "description": s.description,
                "priority": s.priority,
            }
            for s in strategies
        ],
        "prompt": prompt,
        "strategies_path": str(strategies_path) if strategies_path else None,
        "prompt_path": str(prompt_path) if prompt_path else None,
    }
