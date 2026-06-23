"""bob3.structured_uncertainty — Structured-uncertainty clarification loop.

Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing provenance.
In CI mode with no human present, exit SPEC_NEEDS_HUMAN rather than
confabulate.

Public API::

    from bob3.structured_uncertainty import (
        generate_candidate_implementations,
        clarify_ambiguous_slots,
    )
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from spec_synthesis import (
    AskUserQuestion,
    CandidateStub,
    ClarificationAnswer,
    DisagreementSlot,
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    N_CANDIDATES,
    SpecNeedsHumanError,
    compute_disagreement_slots as _compute_disagreement_slots,
    exit_spec_needs_human,
    generate_candidate_stubs,
    run_clarification_loop,
)

__all__ = [
    "generate_candidate_implementations",
    "generate_candidate_stubs",
    "generate_stub_implementations",
    "clarify_ambiguous_slots",
    "detect_slot_ambiguity",
    "trigger_clarification_loop",
    "compute_disagreement_slots",
    "ask_clarification_questions",
    "SPEC_NEEDS_HUMAN",
    "UNCERTAINTY_THRESHOLD",
]


def generate_candidate_implementations(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
) -> list[CandidateStub]:
    """Generate N candidate stub implementations from the draft spec.

    For each "Function defined" or "Class defined" AC, produce
    ``n_candidates`` stubs that vary in return type, raised exceptions,
    and side effects. If stubs disagree on observable behaviour the
    relevant slot is considered ambiguous.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature.
    n_candidates:
        Number of candidate stubs to generate per slot (default 3).

    Returns
    -------
    list[CandidateStub]
        All generated stubs (``n_candidates`` × number of slots).

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list or contains non-string items,
        or if ``n_candidates`` is less than 1.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )
    for item in acceptance_criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"acceptance_criteria items must be strings, got {type(item).__name__}"
            )
    if n_candidates < 1:
        raise ValueError(f"n_candidates must be >= 1, got {n_candidates}")

    return generate_candidate_stubs(acceptance_criteria, n_candidates=n_candidates)


def clarify_ambiguous_slots(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
    threshold: float = UNCERTAINTY_THRESHOLD,
    max_per_round: int = 5,
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
    n_candidates:
        Number of candidate stubs to generate per slot (default 3).
    threshold:
        Uncertainty threshold above which slots trigger clarification (default 0.4).
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When None, reads the ``BOB3_CI_MODE``
        environment variable (truthy values: ``"1"``, ``"true"``, ``"yes"``, ``"on"``).
    audit_log_path:
        Path to the clarifications audit log. Defaults to ``./clarifications.log``.

    Returns
    -------
    dict with keys:
        spec_slots: dict — resolved slot values (may be empty in CI mode).
        outcome: str | None — ``"SPEC_NEEDS_HUMAN"`` when CI mode blocks,
                 ``None`` when the loop completes without ambiguity.
        stubs: list[dict] — generated candidate stubs (one per slot per variant).
        uncertain_slots: list[dict] — slots above the uncertainty threshold.
        uncertainty_threshold: float — the configured threshold (T=0.4).

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list or contains non-string items,
        or if ``n_candidates`` < 1, ``threshold`` outside [0,1], or
        ``max_per_round`` outside [1,5].
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )
    for item in acceptance_criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"acceptance_criteria items must be strings, got {type(item).__name__}"
            )
    if n_candidates < 1:
        raise ValueError(f"n_candidates must be >= 1, got {n_candidates}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    if not 1 <= max_per_round <= 5:
        raise ValueError(f"max_per_round must be in [1, 5], got {max_per_round}")

    # Generate candidate stubs for each function/class slot
    stubs = generate_candidate_stubs(acceptance_criteria, n_candidates=n_candidates)

    # Identify disagreement slots above the uncertainty threshold
    uncertain_slots = _compute_disagreement_slots(stubs, threshold=threshold)

    stubs_serialized = [
        {
            "slot_name": stub.slot_name,
            "return_type": stub.return_type,
            "raised_exceptions": stub.raised_exceptions,
            "side_effects": stub.side_effects,
            "raw_stub": stub.raw_stub,
        }
        for stub in stubs
    ]

    uncertain_slots_serialized = [
        {
            "slot_name": slot.slot_name,
            "provenance": slot.provenance,
            "uncertainty_score": slot.uncertainty_score,
            "candidates": slot.candidates,
            "dimension": slot.dimension,
        }
        for slot in uncertain_slots
    ]

    # In CI mode with uncertain slots, exit rather than confabulate
    if uncertain_slots:
        _ci = ci_mode
        if _ci is None:
            env_val = os.environ.get("BOB3_CI_MODE", "").lower()
            _ci = env_val in ("1", "true", "yes", "on")
        if _ci:
            return {
                "spec_slots": {},
                "outcome": SPEC_NEEDS_HUMAN,
                "stubs": stubs_serialized,
                "uncertain_slots": uncertain_slots_serialized,
                "uncertainty_threshold": threshold,
            }

    if not uncertain_slots:
        return {
            "spec_slots": {},
            "outcome": None,
            "stubs": stubs_serialized,
            "uncertain_slots": uncertain_slots_serialized,
            "uncertainty_threshold": threshold,
        }

    # Interactive mode: run clarification loop
    spec_slots, outcome = run_clarification_loop(
        acceptance_criteria,
        n_candidates=n_candidates,
        ci_mode=ci_mode,
        audit_log_path=audit_log_path,
    )

    return {
        "spec_slots": spec_slots,
        "outcome": outcome,
        "stubs": stubs_serialized,
        "uncertain_slots": uncertain_slots_serialized,
        "uncertainty_threshold": threshold,
    }


def detect_slot_ambiguity(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify ambiguous slots where candidate stubs disagree on observable behaviour.

    Groups ``stubs`` by ``slot_name``, computes a disagreement rate for each
    observable dimension (return type, raised exceptions, side effects), and
    returns slots whose rate exceeds ``threshold``.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4).

    Returns
    -------
    list[DisagreementSlot]
        Slots whose disagreement rate is above ``threshold``.

    Raises
    ------
    ValueError
        If ``stubs`` is not a list or ``threshold`` is outside [0, 1].
    """
    if not isinstance(stubs, list):
        raise ValueError(f"stubs must be a list, got {type(stubs).__name__}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    return _compute_disagreement_slots(stubs, threshold=threshold)


def trigger_clarification_loop(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
    threshold: float = UNCERTAINTY_THRESHOLD,
    max_per_round: int = 5,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Trigger the structured-uncertainty clarification loop.

    Generates N=3 candidate stub implementations; detects ambiguous slots;
    in CI mode raises :class:`SpecNeedsHumanError` rather than confabulating;
    in interactive mode, asks batched multiple-choice questions (1-5 per round)
    citing provenance and folds the answers into ``spec_slots``.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature.
    n_candidates:
        Number of candidate stubs to generate per slot (default 3).
    threshold:
        Uncertainty threshold above which slots trigger clarification (default 0.4).
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When None, reads ``BOB3_CI_MODE`` env var.
    audit_log_path:
        Path to the clarifications audit log.

    Returns
    -------
    tuple[dict[str, Any], str | None]
        ``(spec_slots, "SPEC_NEEDS_HUMAN")`` when CI-blocked, or
        ``(spec_slots, None)`` when the loop completed successfully.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list or contains non-strings,
        or if ``n_candidates`` < 1, ``threshold`` outside [0, 1], or
        ``max_per_round`` outside [1, 5].
    SpecNeedsHumanError
        When CI mode is active and ambiguous slots are present.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )
    for item in acceptance_criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"acceptance_criteria items must be strings, got {type(item).__name__}"
            )
    if n_candidates < 1:
        raise ValueError(f"n_candidates must be >= 1, got {n_candidates}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    if not 1 <= max_per_round <= 5:
        raise ValueError(f"max_per_round must be in [1, 5], got {max_per_round}")

    stubs = generate_candidate_stubs(acceptance_criteria, n_candidates=n_candidates)
    uncertain_slots = _compute_disagreement_slots(stubs, threshold=threshold)

    if uncertain_slots:
        exit_spec_needs_human(uncertain_slots, ci_mode=ci_mode)

    if not uncertain_slots:
        return {}, None

    answers = AskUserQuestion(
        uncertain_slots,
        max_per_round=max_per_round,
        audit_log_path=audit_log_path,
    )

    spec_slots: dict[str, Any] = {}
    for answer in answers:
        slot_entry = spec_slots.setdefault(answer.slot_name, {})
        slot_entry[answer.dimension] = answer.selected
        slot_entry["_clarified_at"] = answer.timestamp

    return spec_slots, None


# ---------------------------------------------------------------------------
# AC-required aliases
# ---------------------------------------------------------------------------


def generate_stub_implementations(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
) -> list[CandidateStub]:
    """Generate N=3 candidate stub implementations from the draft spec.

    Alias for :func:`generate_candidate_implementations` satisfying the
    ``Function defined: bob3.structured_uncertainty.generate_stub_implementations``
    acceptance criterion.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature.
    n_candidates:
        Number of candidate stubs per slot (default 3).

    Returns
    -------
    list[CandidateStub]
        One stub per (slot, variant) pair.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list, contains non-strings, or
        *n_candidates* < 1.
    """
    return generate_candidate_implementations(
        acceptance_criteria, n_candidates=n_candidates
    )


def compute_disagreement_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Groups *stubs* by ``slot_name``, computes a disagreement rate for each
    observable dimension (return type, raised exceptions, side effects), and
    returns slots whose rate exceeds *threshold*.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_stub_implementations`.
    threshold:
        Uncertainty threshold (default T=0.4).

    Returns
    -------
    list[DisagreementSlot]
        Slots above the threshold, sorted deterministically.

    Raises
    ------
    ValueError
        If *stubs* is not a list or *threshold* is outside [0, 1].
    """
    if not isinstance(stubs, list):
        raise ValueError(f"stubs must be a list, got {type(stubs).__name__}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    return _compute_disagreement_slots(stubs, threshold=threshold)


def ask_clarification_questions(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = 5,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> list[ClarificationAnswer]:
    """Ask batched multiple-choice clarification questions for ambiguous slots.

    Each question cites the provenance span of the ambiguity so the human
    respondent has full context. At most *max_per_round* questions are
    presented per round.

    In CI mode (no human present), raises :class:`SpecNeedsHumanError`
    rather than confabulating answers.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold as returned by
        :func:`compute_disagreement_slots`.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When ``None``, reads ``BOB3_CI_MODE`` env var.
    audit_log_path:
        Path to the clarifications audit log.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per slot (interactive mode), or empty list when no slots.

    Raises
    ------
    SpecNeedsHumanError
        When CI mode is active and *disagreement_slots* is non-empty.
    ValueError
        If *disagreement_slots* is not a list or *max_per_round* outside [1, 5].
    """
    if not isinstance(disagreement_slots, list):
        raise ValueError(
            f"disagreement_slots must be a list, got {type(disagreement_slots).__name__}"
        )
    if not 1 <= max_per_round <= 5:
        raise ValueError(f"max_per_round must be in [1, 5], got {max_per_round}")

    if not disagreement_slots:
        return []

    exit_spec_needs_human(disagreement_slots, ci_mode=ci_mode)

    return AskUserQuestion(
        disagreement_slots,
        max_per_round=max_per_round,
        audit_log_path=audit_log_path,
    )
