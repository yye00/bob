"""Brownfield elicitation dispatcher — integration of BF-3 into the orchestrator.

AC: integration: bob.brownfield.dispatcher

This module wires the BF-3 elicitation classifier + clarification-budget gate
into the bob orchestrator dispatch loop. It provides the canonical entry point
for dispatching a brownfield intent through:
  1. extract_intent() — classify the raw user prompt into a BrownfieldIntent.
  2. score_ambiguity() — score ambiguity via k-sample stub consistency.
  3. should_ask_user() — determine if the gate should emit AskUserQuestion.
  4. apply_clarification_gate() — apply the 3-rule ASK/ASSUME/BRANCH policy.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from bob.brownfield.elicit import (
    BrownfieldIntent,
    ClarificationGateResult,
    apply_clarification_gate,
    extract_intent,
    score_ambiguity,
    should_ask_user,
)

logger = logging.getLogger(__name__)


def dispatch_elicitation(
    user_prompt: str,
    *,
    is_headless: bool = False,
    k_samples: int = 3,
) -> dict[str, Any]:
    """Dispatch a free-text brownfield user prompt through the BF-3 elicitation pipeline.

    Orchestrator integration point for BF-3. Runs:
      1. extract_intent — classify raw user prompt into BrownfieldIntent.
      2. score_ambiguity — k-sample stub consistency scoring.
      3. apply_clarification_gate — 3-rule ASK/ASSUME/BRANCH policy.

    Args:
        user_prompt:  Raw, verbatim user request text.
        is_headless:  True when running under ``claude -p`` (headless mode).
                      Headless workers must take BRANCH path; ASK is reserved
                      for interactive ``bob init`` shell.
        k_samples:    Number of candidate stubs for ambiguity scoring.

    Returns:
        dict with keys:
          intent  — serialized BrownfieldIntent fields.
          gate    — serialized ClarificationGateResult (action, questions, etc.).
          should_ask — bool, True only in interactive mode with external ambiguity.

    Raises:
        TypeError:  If user_prompt is None.
        ValueError: If user_prompt is not a string.
    """
    if user_prompt is None:
        raise TypeError("user_prompt must be a string, got None")
    if not isinstance(user_prompt, str):
        raise ValueError(
            f"user_prompt must be str, got {type(user_prompt).__name__!r}"
        )

    intent: BrownfieldIntent = extract_intent(user_prompt)
    intent = score_ambiguity(intent, k=k_samples)
    ask = should_ask_user(intent, is_headless=is_headless)
    gate: ClarificationGateResult = apply_clarification_gate(intent, is_headless=is_headless)

    logger.debug(
        "BF-3 dispatch: intent_kind=%s ambiguity=%.3f gate=%s ask=%s",
        intent.intent_kind,
        intent.ambiguity_score,
        gate.action,
        ask,
    )

    return {
        "intent": {
            "intent_kind": intent.intent_kind,
            "capability": intent.capability,
            "target_subsystem": intent.target_subsystem,
            "mechanism": intent.mechanism,
            "provider": intent.provider,
            "jtbd": {
                "situation": intent.jtbd.situation,
                "motivation": intent.jtbd.motivation,
                "outcome": intent.jtbd.outcome,
            },
            "acceptance_criteria": intent.acceptance_criteria,
            "ambiguity_score": intent.ambiguity_score,
            "ambiguity_loci": intent.ambiguity_loci,
            "user_prompt_raw": intent.user_prompt_raw,
        },
        "gate": {
            "action": gate.action,
            "questions": gate.questions,
            "assumption_record": gate.assumption_record,
            "branch_candidates": gate.branch_candidates,
        },
        "should_ask": ask,
    }


__all__ = [
    "dispatch_elicitation",
    "extract_intent",
    "score_ambiguity",
    "should_ask_user",
    "apply_clarification_gate",
]
