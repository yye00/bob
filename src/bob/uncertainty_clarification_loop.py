"""Structured-uncertainty clarification loop with AskUserQuestion.

Feature: 25705219-4c54-4522-b556-adfad3c72f08

Generate N=3 candidate stub implementations from the draft spec; if they
disagree on observable behaviour (return type, raised exceptions, side
effects), mark the relevant slot ambiguous. Slots above uncertainty
threshold T=0.4 trigger a batched (1-5 per round) multiple-choice question
citing provenance. In CI mode with no human present, exit SPEC_NEEDS_HUMAN
rather than confabulate.

Public API::

    from bob.uncertainty_clarification_loop import (
        generate_candidate_stubs,
        mark_ambiguous_slots,
        build_clarification_questions,
    )

The stub-synthesis and disagreement-scoring primitives are shared with
``spec_synthesis`` (single source of truth); this module adds the
provenance-citing question builder and CI-mode gating required by the
feature spec.
"""

from __future__ import annotations

from dataclasses import dataclass

from spec_synthesis import (
    CandidateStub,
    ClarificationAnswer,
    DisagreementSlot,
    N_CANDIDATES,
    SPEC_NEEDS_HUMAN,
    SpecNeedsHumanError,
    UNCERTAINTY_THRESHOLD,
    compute_disagreement_slots as _compute_disagreement_slots,
    exit_spec_needs_human as _exit_spec_needs_human,
    generate_candidate_stubs as _generate_candidate_stubs,
)

MAX_QUESTIONS_PER_ROUND = 5

__all__ = [
    "CandidateStub",
    "ClarificationAnswer",
    "ClarificationQuestion",
    "DisagreementSlot",
    "SPEC_NEEDS_HUMAN",
    "SpecNeedsHumanError",
    "UNCERTAINTY_THRESHOLD",
    "N_CANDIDATES",
    "MAX_QUESTIONS_PER_ROUND",
    "generate_candidate_stubs",
    "mark_ambiguous_slots",
    "build_clarification_questions",
]


@dataclass
class ClarificationQuestion:
    """A single provenance-citing multiple-choice question for a slot."""

    slot_name: str
    provenance: str
    question_text: str
    choices: list[str]  # 2-4 candidates + "Other"
    dimension: str


def generate_candidate_stubs(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
) -> list[CandidateStub]:
    """Generate N candidate stub implementations from the draft spec.

    For each "Function defined" / "Class defined" AC, produce
    ``n_candidates`` stubs that vary in return type, raised exceptions,
    and side effects. Non-function ACs (e.g. "File exists") contribute no
    slots and therefore no stubs.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature.
    n_candidates:
        Number of candidate stubs to generate per slot (default 3).

    Returns
    -------
    list[CandidateStub]
        All generated stubs (``n_candidates`` × number of slots). Empty
        list when no function/class slots are present.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, contains non-string
        items, or ``n_candidates`` is less than 1.
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


def mark_ambiguous_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Mark slots ambiguous when candidate stubs disagree on behaviour.

    Groups ``stubs`` by slot name and computes a disagreement rate per
    observable dimension (return type, raised exceptions, side effects).
    Slots whose rate exceeds ``threshold`` are returned, sorted by slot
    name and dimension for deterministic ordering.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4).

    Returns
    -------
    list[DisagreementSlot]
        Slots above the uncertainty threshold (empty when all agree).

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


def build_clarification_questions(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = MAX_QUESTIONS_PER_ROUND,
    ci_mode: bool | None = None,
) -> list[ClarificationQuestion]:
    """Build batched multiple-choice questions citing provenance.

    Each ambiguous slot yields one question presenting 2-4 candidate
    values plus an "Other" option, with the provenance span of the
    ambiguity cited in the question text. Questions are ordered so that
    consumers can present them in rounds of at most ``max_per_round``.

    In CI mode (no human present), this raises :class:`SpecNeedsHumanError`
    (surfacing the ``SPEC_NEEDS_HUMAN`` sentinel) whenever ambiguous slots
    are present, rather than confabulating an answer. An empty slot list
    always returns ``[]`` — even in CI mode — because there is nothing to
    block on.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold, from
        :func:`mark_ambiguous_slots`.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When ``None``, reads the ``BOB_CI_MODE``
        environment variable.

    Returns
    -------
    list[ClarificationQuestion]
        One question per slot (empty when no slots).

    Raises
    ------
    ValueError
        If ``disagreement_slots`` is not a list or ``max_per_round`` is
        outside [1, 5].
    SpecNeedsHumanError
        When CI mode is active and ``disagreement_slots`` is non-empty.
    """
    if not isinstance(disagreement_slots, list):
        raise ValueError(
            f"disagreement_slots must be a list, got {type(disagreement_slots).__name__}"
        )
    if not 1 <= max_per_round <= MAX_QUESTIONS_PER_ROUND:
        raise ValueError(
            f"max_per_round must be in [1, {MAX_QUESTIONS_PER_ROUND}], got {max_per_round}"
        )

    if not disagreement_slots:
        return []

    # CI gate: never confabulate when no human is present.
    _exit_spec_needs_human(disagreement_slots, ci_mode=ci_mode)

    questions: list[ClarificationQuestion] = []
    for slot in disagreement_slots:
        unique_cands = list(dict.fromkeys(slot.candidates))[:3]
        choices = unique_cands + ["Other"]
        question_text = (
            f"[{slot.provenance}] Ambiguous {slot.dimension} for "
            f"`{slot.slot_name}` (uncertainty={slot.uncertainty_score:.2f}):\n"
            "  Which observable value is correct?"
        )
        questions.append(
            ClarificationQuestion(
                slot_name=slot.slot_name,
                provenance=slot.provenance,
                question_text=question_text,
                choices=choices,
                dimension=slot.dimension,
            )
        )
    return questions
