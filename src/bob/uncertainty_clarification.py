"""bob.uncertainty_clarification — Structured-uncertainty clarification loop.

Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing provenance.
In CI mode with no human present, exit SPEC_NEEDS_HUMAN rather than
confabulate.

Public API::

    from bob.uncertainty_clarification import (
        generate_candidate_stubs,
        identify_ambiguous_slots,
        trigger_clarification_loop,
    )

Integration with bob.spec_synthesizer::

    from bob.uncertainty_clarification import trigger_clarification_loop
    spec_slots, outcome = trigger_clarification_loop(acceptance_criteria, ci_mode=True)
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
    generate_candidate_stubs as _generate_candidate_stubs,
    run_clarification_loop as _run_clarification_loop,
)

__all__ = [
    "generate_candidate_stubs",
    "identify_ambiguous_slots",
    "detect_ambiguous_slots",
    "build_clarification_question",
    "trigger_clarification_loop",
    "SPEC_NEEDS_HUMAN",
    "UNCERTAINTY_THRESHOLD",
    "N_CANDIDATES",
    "CandidateStub",
    "DisagreementSlot",
    "ClarificationAnswer",
    "SpecNeedsHumanError",
]


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

    return _generate_candidate_stubs(acceptance_criteria, n_candidates=n_candidates)


def identify_ambiguous_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Groups ``stubs`` by ``slot_name``, then computes a disagreement rate
    for each observable dimension (return type, raised exceptions, side
    effects). Slots whose disagreement rate exceeds ``threshold`` are
    returned as ambiguous.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4). Slots with disagreement
        rate above this value are flagged as ambiguous.

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


def detect_ambiguous_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Detect slots where candidate stubs disagree on observable behaviour.

    Alias for :func:`identify_ambiguous_slots` using the AC-specified name.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4). Slots with disagreement
        rate above this value are flagged as ambiguous.

    Returns
    -------
    list[DisagreementSlot]
        Slots whose disagreement rate is above ``threshold``.

    Raises
    ------
    ValueError
        If ``stubs`` is not a list or ``threshold`` is outside [0, 1].
    """
    return identify_ambiguous_slots(stubs, threshold=threshold)


def build_clarification_question(
    slot: DisagreementSlot,
    *,
    max_choices: int = 5,
) -> dict:
    """Build a multiple-choice clarification question for a single ambiguous slot.

    Produces a structured question dict suitable for presentation to the user
    or logging, citing the slot's provenance span. The question is batched
    together with others in :func:`trigger_clarification_loop`.

    Parameters
    ----------
    slot:
        An ambiguous :class:`~spec_synthesis.DisagreementSlot` whose
        ``uncertainty_score`` exceeds the threshold T=0.4.
    max_choices:
        Maximum number of candidate choices to include (default 5).

    Returns
    -------
    dict
        A dict with keys:
        - ``slot_name``: str
        - ``dimension``: str
        - ``provenance``: str — cite the AC source span
        - ``uncertainty_score``: float
        - ``choices``: list[str] — deduplicated candidates (≤ max_choices)
        - ``question``: str — human-readable question text

    Raises
    ------
    ValueError
        If ``slot`` is not a :class:`~spec_synthesis.DisagreementSlot`,
        or ``max_choices`` is less than 1.
    """
    if not isinstance(slot, DisagreementSlot):
        raise ValueError(
            f"slot must be a DisagreementSlot, got {type(slot).__name__}"
        )
    if max_choices < 1:
        raise ValueError(f"max_choices must be >= 1, got {max_choices}")

    unique_candidates = list(dict.fromkeys(slot.candidates))[:max_choices]
    choices_text = ", ".join(f"({i + 1}) {c}" for i, c in enumerate(unique_candidates))
    question = (
        f"Ambiguity detected in '{slot.slot_name}' [{slot.dimension}] "
        f"(provenance: {slot.provenance}, score: {slot.uncertainty_score:.2f}). "
        f"Which value should be used? {choices_text}"
    )
    return {
        "slot_name": slot.slot_name,
        "dimension": slot.dimension,
        "provenance": slot.provenance,
        "uncertainty_score": slot.uncertainty_score,
        "choices": unique_candidates,
        "question": question,
    }


def trigger_clarification_loop(
    acceptance_criteria: list[str],
    spec_slots: dict[str, Any] | None = None,
    *,
    n_candidates: int = N_CANDIDATES,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Run the structured-uncertainty clarification loop.

    Orchestrates the full pipeline:

    1. :func:`generate_candidate_stubs` — produce N stubs per slot.
    2. :func:`identify_ambiguous_slots` — find slots above T=0.4.
    3. If CI mode and any disagreement → return ``(spec_slots, SPEC_NEEDS_HUMAN)``.
    4. :func:`spec_synthesis.AskUserQuestion` — collect answers interactively.
    5. Fold answers back into ``spec_slots``.

    In CI mode (``BOB_CI_MODE=1`` or ``ci_mode=True``) with any ambiguous
    slots, returns ``SPEC_NEEDS_HUMAN`` rather than confabulating an answer.

    Integration with ``bob.spec_synthesizer``::

        from bob.uncertainty_clarification import trigger_clarification_loop

        spec_slots, outcome = trigger_clarification_loop(
            feature["acceptance_criteria"],
            ci_mode=True,
        )
        if outcome == "SPEC_NEEDS_HUMAN":
            raise RuntimeError("Feature spec is ambiguous — human review required")

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature being synthesised.
    spec_slots:
        Existing spec-slot dict to fold clarification answers into.
        Defaults to an empty dict.
    n_candidates:
        Number of candidate stubs to generate per slot (default 3).
    ci_mode:
        Force CI mode on/off; ``None`` reads the ``BOB_CI_MODE``
        environment variable (truthy: ``"1"``, ``"true"``, ``"yes"``, ``"on"``).
    audit_log_path:
        Path to the ``clarifications.log`` audit trail.

    Returns
    -------
    tuple[dict[str, Any], str | None]
        ``(spec_slots, "SPEC_NEEDS_HUMAN")`` when CI-blocked, or
        ``(spec_slots, None)`` when the loop completed successfully.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list or contains non-strings.
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

    return _run_clarification_loop(
        acceptance_criteria,
        spec_slots,
        n_candidates=n_candidates,
        ci_mode=ci_mode,
        audit_log_path=audit_log_path,
    )
