"""BF-3 — Elicitation classifier + clarification-budget gate.

Intent-research synthesis (ae2a9.. + a9eaa..). Converts free-text user
requests into the BrownfieldIntent schema, scores ambiguity via k-sample
stub consistency (ClarifyGPT style), and gates AskUserQuestion invocation
by value-of-information.

This module is the canonical entry point wired into the orchestrator.
It delegates to src/bob/brownfield/elicit.py for the core logic.

Clarification gate (3-rule policy):
  - ASK   — external bindings (package, provider, persistence, public API).
             Cap 2 questions/stub. Interactive only.
  - ASSUME — internal/reversible (naming, layout, helper sigs).
             Log to assumption_record.
  - BRANCH — (default) ≥2 interpretations with comparable prior.
             Emit N stubs tagged interpretation=A|B.
             Also used when headless and ASK would otherwise apply.
"""

from __future__ import annotations

from typing import Any

from bob.brownfield.elicit import (  # noqa: F401 — integration AC 47112d92
    BrownfieldIntent,
    ClarificationGateResult,
    JTBDSlot,
    apply_clarification_gate,
    classify_intent,
    score_ambiguity,
)


def bf_3_elicitation_classifier_clarification_budget_gate(
    user_prompt: str,
    *,
    is_headless: bool = False,
    k_samples: int = 3,
) -> dict[str, Any]:
    """Classify a free-text brownfield intent and apply the clarification gate.

    Accepts a raw user prompt, extracts a BrownfieldIntent, scores its
    ambiguity via k-sample stub consistency, and applies the 3-rule
    clarification gate.

    Boundary conditions:
      - Empty or whitespace-only prompt → returns default classified intent
        (intent_kind='add') with no crash.
      - None or non-string prompt → raises TypeError/ValueError.

    Args:
        user_prompt:  Raw, verbatim user request text.
        is_headless:  True when running under ``claude -p`` (no human).
                      ASK is reserved for interactive; headless demotes to BRANCH.
        k_samples:    Number of candidate stubs for ambiguity scoring (default 3).

    Returns:
        Dict with keys:
          intent:  dict representation of the classified BrownfieldIntent.
          gate:    dict representation of the ClarificationGateResult.

    Raises:
        TypeError:  If user_prompt is None.
        ValueError: If user_prompt is not a string type.
    """
    if user_prompt is None:
        raise TypeError("user_prompt must be a string, got None")
    if not isinstance(user_prompt, str):
        raise ValueError(
            f"user_prompt must be a str, got {type(user_prompt).__name__!r}"
        )

    # Normalize whitespace-only to empty string; both are valid inputs.
    normalized_prompt = user_prompt.strip()

    # Classify intent.
    intent: BrownfieldIntent = classify_intent(normalized_prompt)

    # Score ambiguity via k-sample stub consistency.
    intent = score_ambiguity(intent, k=k_samples)

    # Apply the 3-rule clarification gate.
    gate: ClarificationGateResult = apply_clarification_gate(
        intent, is_headless=is_headless
    )

    return {
        "intent": _intent_to_dict(intent),
        "gate": _gate_to_dict(gate),
    }


def _intent_to_dict(intent: BrownfieldIntent) -> dict[str, Any]:
    """Serialize BrownfieldIntent to a plain dict."""
    return {
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
    }


def _gate_to_dict(gate: ClarificationGateResult) -> dict[str, Any]:
    """Serialize ClarificationGateResult to a plain dict."""
    return {
        "action": gate.action,
        "questions": gate.questions,
        "assumption_record": gate.assumption_record,
        "branch_candidates": gate.branch_candidates,
    }


__all__ = [
    "bf_3_elicitation_classifier_clarification_budget_gate",
    "BrownfieldIntent",
    "ClarificationGateResult",
    "JTBDSlot",
    "classify_intent",
    "score_ambiguity",
    "apply_clarification_gate",
]
