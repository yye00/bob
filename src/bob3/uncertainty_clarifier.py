"""Structured-uncertainty clarification loop with AskUserQuestion.

Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing provenance.
In CI mode with no human present, exit SPEC_NEEDS_HUMAN rather than
confabulate.

Public API::

    from bob3.uncertainty_clarifier import (
        generate_candidate_stubs,
        detect_disagreement_slots,
        format_ambiguity_question,
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_synthesis import (
    AskUserQuestion,
    CandidateStub,
    ClarificationAnswer,
    DisagreementSlot,
    N_CANDIDATES,
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    SpecNeedsHumanError,
    compute_disagreement_slots as _compute_disagreement_slots,
    exit_spec_needs_human,
    generate_candidate_stubs as _generate_candidate_stubs,
)
from spec_synthesis import MAX_QUESTIONS_PER_ROUND

__all__ = [
    "generate_candidate_stubs",
    "detect_disagreement",
    "detect_disagreement_slots",
    "ask_clarification_batch",
    "format_ambiguity_question",
]

import bob3.spec_loader as _spec_loader  # noqa: F401 — integration: bob3.spec_loader


def generate_candidate_stubs(
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
        If ``acceptance_criteria`` is not a list, contains non-string items,
        or ``n_candidates`` is less than 1.
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

    return _generate_candidate_stubs(acceptance_criteria, n_candidates=n_candidates)


def detect_disagreement_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Groups ``stubs`` by ``slot_name``, then computes a disagreement rate
    for each observable dimension (return type, raised exceptions, side
    effects). Slots whose rate exceeds ``threshold`` are returned and
    considered ambiguous.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4). Must be in [0, 1].

    Returns
    -------
    list[DisagreementSlot]
        Slots whose disagreement rate is above ``threshold``, sorted by
        slot name and dimension for deterministic ordering.

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


def detect_disagreement(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Alias for :func:`detect_disagreement_slots`.

    Provided for AC compatibility: ``Function defined:
    bob3.uncertainty_clarifier.detect_disagreement``.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4). Must be in [0, 1].

    Returns
    -------
    list[DisagreementSlot]
        Slots whose disagreement rate is above ``threshold``.

    Raises
    ------
    ValueError
        If ``stubs`` is not a list or ``threshold`` is outside [0, 1].
    """
    return detect_disagreement_slots(stubs, threshold=threshold)


def ask_clarification_batch(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = MAX_QUESTIONS_PER_ROUND,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> list[ClarificationAnswer]:
    """Present batched multiple-choice clarification questions for ambiguous slots.

    Slots above the uncertainty threshold (T=0.4) trigger multiple-choice
    questions in rounds of at most ``max_per_round`` (1-5), each citing
    the provenance of the ambiguity.  In CI mode (or when ``BOB3_CI_MODE``
    is set and no human is present) this function raises
    :exc:`~spec_synthesis.SpecNeedsHumanError` with the ``SPEC_NEEDS_HUMAN``
    sentinel rather than confabulating answers.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold, as returned by
        :func:`detect_disagreement_slots`.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off; ``None`` reads the ``BOB3_CI_MODE``
        environment variable (any non-empty value → CI mode active).
    audit_log_path:
        Path to the ``clarifications.log`` audit trail.

    Returns
    -------
    list[ClarificationAnswer]
        One resolved answer per disagreement slot.

    Raises
    ------
    ValueError
        If ``disagreement_slots`` is not a list, or ``max_per_round`` is
        outside [1, 5].
    SpecNeedsHumanError
        If CI mode is active and ``disagreement_slots`` is non-empty.
    """
    import os

    if not isinstance(disagreement_slots, list):
        raise ValueError(
            f"disagreement_slots must be a list, got {type(disagreement_slots).__name__}"
        )
    if not 1 <= max_per_round <= MAX_QUESTIONS_PER_ROUND:
        raise ValueError(
            f"max_per_round must be in [1, {MAX_QUESTIONS_PER_ROUND}], got {max_per_round}"
        )

    if ci_mode is None:
        ci_mode = bool(os.environ.get("BOB3_CI_MODE", ""))

    if ci_mode and disagreement_slots:
        raise SpecNeedsHumanError(
            f"SPEC_NEEDS_HUMAN: {len(disagreement_slots)} ambiguous slot(s) require human "
            "clarification but CI mode is active (no human present)."
        )

    if not disagreement_slots:
        return []

    return AskUserQuestion(
        disagreement_slots,
        max_per_round=max_per_round,
        audit_log_path=audit_log_path,
    )


def format_ambiguity_question(
    slot: DisagreementSlot,
    *,
    max_choices: int = 3,
) -> dict[str, Any]:
    """Format a structured multiple-choice question for one ambiguous slot.

    Produces a dict suitable for display (or serialisation to JSON) with
    the slot provenance, uncertainty score, and a capped list of candidate
    answer choices (plus "Other").

    Parameters
    ----------
    slot:
        One :class:`~spec_synthesis.DisagreementSlot` above the
        uncertainty threshold.
    max_choices:
        Maximum number of candidate answers to include before the
        "Other" option (default 3).

    Returns
    -------
    dict with keys:
        provenance: str — e.g. ``"F-R7-451"``.
        slot_name: str — e.g. ``"compute_score"``.
        dimension: str — e.g. ``"return_type"``.
        uncertainty_score: float — disagreement rate in [0, 1].
        question: str — human-readable question text citing provenance.
        choices: list[str] — candidate answers, always ending with ``"Other"``.

    Raises
    ------
    ValueError
        If ``slot`` is not a :class:`~spec_synthesis.DisagreementSlot` or
        ``max_choices`` is less than 1.
    """
    if not isinstance(slot, DisagreementSlot):
        raise ValueError(
            f"slot must be a DisagreementSlot, got {type(slot).__name__}"
        )
    if max_choices < 1:
        raise ValueError(f"max_choices must be >= 1, got {max_choices}")

    unique_candidates = list(dict.fromkeys(slot.candidates))[:max_choices]
    choices = unique_candidates + ["Other"]

    question = (
        f"[{slot.provenance}] Ambiguous {slot.dimension} for `{slot.slot_name}` "
        f"(uncertainty={slot.uncertainty_score:.2f}): "
        "Which observable value is correct?"
    )

    return {
        "provenance": slot.provenance,
        "slot_name": slot.slot_name,
        "dimension": slot.dimension,
        "uncertainty_score": slot.uncertainty_score,
        "question": question,
        "choices": choices,
    }
