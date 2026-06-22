"""Structured-uncertainty clarification loop with AskUserQuestion.

Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing provenance.
In CI mode with no human present, exit SPEC_NEEDS_HUMAN rather than
confabulate.

Public API::

    from bob3.structured_uncertainty_clarification_loop_askuserquestion import (
        structured_uncertainty_clarification_loop_askuserquestion,
    )

    result = structured_uncertainty_clarification_loop_askuserquestion(
        acceptance_criteria=[...],
        ci_mode=True,
    )
    if result["outcome"] == "SPEC_NEEDS_HUMAN":
        raise RuntimeError("Spec needs human review before codegen can proceed")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.clarification_loop import (
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    code_consistency_check,
    run_clarification_loop,
)


def structured_uncertainty_clarification_loop_askuserquestion(
    acceptance_criteria: list[str],
    *,
    n_stubs: int = 3,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run the structured-uncertainty clarification loop.

    Generates N=3 candidate stub implementations for each function slot
    extracted from the acceptance criteria. If stubs disagree on observable
    behaviour (return type, raised exceptions, side effects), the slot is
    marked ambiguous. Slots above uncertainty threshold T=0.4 trigger
    batched multiple-choice questions citing provenance.

    In CI mode (no human present), exits with SPEC_NEEDS_HUMAN rather than
    confabulating answers.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature (e.g. ``"Function defined: ..."``).
    n_stubs:
        Number of candidate stubs to generate per slot (default 3).
    ci_mode:
        Force CI mode on/off. When None, reads the ``BOB3_CI_MODE``
        environment variable (truthy values: ``"1"``, ``"true"``, ``"yes"``, ``"on"``).
    audit_log_path:
        Path to the clarifications audit log. Defaults to
        ``./clarifications.log``.

    Returns
    -------
    dict with keys:
        spec_slots: dict — resolved slot values (may be empty in CI mode).
        outcome: str | None — ``"SPEC_NEEDS_HUMAN"`` when CI mode blocks,
                 ``None`` when the loop completes without ambiguity.
        stubs: list[dict] — generated candidate stubs (one per slot per variant).
        uncertain_slots: list[dict] — slots above the uncertainty threshold.
        uncertainty_threshold: float — the configured threshold (T=0.4).
    """
    report = code_consistency_check(
        acceptance_criteria,
        n_stubs=n_stubs,
        ci_mode=ci_mode,
    )

    uncertain_slots_serialized = [
        {
            "slot_name": slot.slot_name,
            "provenance": slot.provenance,
            "uncertainty_score": slot.uncertainty_score,
            "candidates": slot.candidates,
            "dimension": slot.dimension,
        }
        for slot in report.uncertain_slots
    ]

    stubs_serialized = [
        {
            "slot_name": stub.slot_name,
            "return_type": stub.return_type,
            "raised_exceptions": stub.raised_exceptions,
            "side_effects": stub.side_effects,
            "raw_stub": stub.raw_stub,
        }
        for stub in report.stubs
    ]

    if report.spec_needs_human:
        return {
            "spec_slots": {},
            "outcome": SPEC_NEEDS_HUMAN,
            "stubs": stubs_serialized,
            "uncertain_slots": uncertain_slots_serialized,
            "uncertainty_threshold": UNCERTAINTY_THRESHOLD,
        }

    spec_slots, outcome = run_clarification_loop(
        acceptance_criteria,
        n_stubs=n_stubs,
        ci_mode=ci_mode,
        audit_log_path=audit_log_path,
    )

    return {
        "spec_slots": spec_slots,
        "outcome": outcome,
        "stubs": stubs_serialized,
        "uncertain_slots": uncertain_slots_serialized,
        "uncertainty_threshold": UNCERTAINTY_THRESHOLD,
    }
