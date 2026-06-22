"""Structured-uncertainty clarification loop with AskUserQuestion.

Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing provenance.
In CI mode with no human present, exit SPEC_NEEDS_HUMAN rather than
confabulate.

Public API::

    from spec_synthesis.uncertainty_clarifier import (
        generate_candidate_stubs,
        identify_ambiguous_slots,
        trigger_user_clarification,
    )
"""

from __future__ import annotations

from pathlib import Path

from spec_synthesis import (
    AskUserQuestion,
    CandidateStub,
    ClarificationAnswer,
    DisagreementSlot,
    N_CANDIDATES,
    UNCERTAINTY_THRESHOLD,
    SpecNeedsHumanError,
    compute_disagreement_slots as _compute_disagreement_slots,
    exit_spec_needs_human,
    generate_candidate_stubs as _generate_candidate_stubs,
)


def generate_candidate_stubs(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
) -> list[CandidateStub]:
    """Generate N candidate stub implementations from the draft spec.

    For each "Function defined" or "Class defined" AC, produce
    ``n_candidates`` stubs that vary in return type, raised exceptions,
    and side effects.  If stubs disagree on observable behaviour the
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


def identify_ambiguous_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Groups ``stubs`` by ``slot_name``, then computes a disagreement rate
    for each observable dimension (return type, raised exceptions, side
    effects).  Slots whose rate exceeds ``threshold`` are returned and
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


def trigger_user_clarification(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = 5,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> list[ClarificationAnswer]:
    """Trigger batched clarification questions for ambiguous slots.

    Slots above uncertainty threshold T=0.4 trigger batched (1-5 per round)
    multiple-choice questions citing provenance.  In CI mode with no human
    present, raises :class:`SpecNeedsHumanError` (SPEC_NEEDS_HUMAN sentinel)
    rather than confabulate.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold, as returned by
        :func:`identify_ambiguous_slots`.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When ``None``, reads the ``BOB3_CI_MODE``
        environment variable.
    audit_log_path:
        Path to the ``clarifications.log`` audit trail.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per disagreement slot (interactive or non-TTY auto mode),
        or an empty list when ``disagreement_slots`` is empty.

    Raises
    ------
    SpecNeedsHumanError
        When CI mode is active and ``disagreement_slots`` is non-empty.
    ValueError
        If ``disagreement_slots`` is not a list or ``max_per_round`` is
        outside [1, 5].
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
