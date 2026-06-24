"""Facade for research-augmented retry — path-finding on ambiguous AC failure.

When refinement_attempts >= 2 AND the previous attempt's failure is
classifiable, spawn a research sub-agent that surfaces 1-2 alternative
strategies tailored to the failure class. Inject strategies into the next
implementer's prompt prefix. The implementer retries with NEW information.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob.orchestrator.path_finding_retry import (
    FailureClass,
    Strategy,
    cache_strategies_per_attempt,
    classify_failure,
    inject_into_implementer_prompt,
    persist_implementer_prompt,
    research_strategies,
    should_trigger,
)


def research_augmented_retry_path_finding_ambiguous_ac_failure(
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
    """
    triggered = should_trigger(refinement_attempts, failure_info)

    failure_class = classify_failure(failure_info)
    strategies: list[Strategy] = []
    strategies_path: pathlib.Path | None = None
    prompt_path: pathlib.Path | None = None
    prompt = base_prompt

    if triggered:
        strategies = research_strategies(failure_class)
        prompt = inject_into_implementer_prompt(
            base_prompt=base_prompt,
            strategies=strategies,
            failure_class=failure_class,
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
        "failure_class": failure_class.value,
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
