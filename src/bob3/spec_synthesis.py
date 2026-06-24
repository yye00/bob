"""bob3.spec_synthesis — Structured-uncertainty clarification loop with AskUserQuestion.

Feature: 45b6c6b9-9701-4baa-ab0f-59af7d2cee18

Generate N=3 candidate stub implementations from the draft spec; if they
disagree on observable behaviour, mark the relevant slot ambiguous. Slots
above uncertainty threshold T=0.4 trigger a batched (1-5 per round)
multiple-choice question citing provenance.  In CI mode with no human
present, exit SPEC_NEEDS_HUMAN rather than confabulate.

Also includes the N-sample stability check pre-critic (feature 9ad637e2):
run_parallel_extraction, normalize_variants, compute_jaccard_stability,
route_by_stability.

Public API::

    from bob3.spec_synthesis import (
        generate_candidate_implementations,
        compute_disagreement_slots,
        format_clarification_question,
        run_parallel_extraction,
        normalize_variants,
        compute_jaccard_stability,
        route_by_stability,
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
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    N_CANDIDATES,
    SpecNeedsHumanError,
    compute_disagreement_slots as _compute_disagreement_slots,
    exit_spec_needs_human,
    generate_candidate_stubs,
    run_clarification_loop,
)
from bob3.spec_synthesizer import (
    _ensure_boundary_and_error_coverage as _ensure_bec,
    deterministic_fallback as _deterministic_fallback,
)
from bob3.spec_quality.example_grammar import (
    KeyExample,
    PropertyAC,
    BoundaryRequirement,
    MissingBoundaryError,
    check_boundary_satisfied,
    parse_property_ac as _parse_property_ac,
    parse_key_example as _parse_key_example,
    requires_boundary as _requires_boundary,
)
from ac_grammar.property_based import (
    parse_property_ac as _ac_parse_property_ac,
    parse_key_example_ac as _ac_parse_key_example_ac,
)
from bob3.self_discover_meta_agent import (
    select_spec_sections as _select_spec_sections,
    extract_with_focused_sections as _extract_with_focused_sections,
)

__all__ = [
    "generate_candidate_implementations",
    "generate_candidates",
    "generate_candidate_stubs",
    "compute_disagreement_slots",
    "compute_uncertainty",
    "format_clarification_question",
    "ask_for_clarification",
    "trigger_clarification_questions",
    "run_clarification_loop",
    "ensure_boundary_and_error_coverage",
    "deterministic_fallback",
    "emit_plan_ready_event",
    "parse_property_ac",
    "parse_key_example_ac",
    "validate_boundary_examples",
    "SPEC_NEEDS_HUMAN",
    "UNCERTAINTY_THRESHOLD",
    "N_CANDIDATES",
    "CandidateStub",
    "DisagreementSlot",
    "ClarificationAnswer",
    "SpecNeedsHumanError",
    "PropertyAC",
    "KeyExample",
    "BoundaryRequirement",
    "MissingBoundaryError",
    "select_spec_sections",
    "extract_with_focused_sections",
]


#: Re-exported from bob3.self_discover_meta_agent for spec_synthesis consumers.
select_spec_sections = _select_spec_sections

#: Re-exported from bob3.self_discover_meta_agent for spec_synthesis consumers.
extract_with_focused_sections = _extract_with_focused_sections


def generate_candidate_implementations(
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


def compute_disagreement_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Groups ``stubs`` by ``slot_name``, then computes a disagreement rate
    for each observable dimension (return type, raised exceptions, side
    effects).  Slots whose rate exceeds ``threshold`` are returned.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_implementations`.
    threshold:
        Uncertainty threshold (default T=0.4).

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


def format_clarification_question(
    slot: DisagreementSlot,
    *,
    question_number: int = 1,
    total_questions: int = 1,
) -> str:
    """Format a multiple-choice clarification question for one ambiguous slot.

    Produces a human-readable question string citing the provenance span
    of the ambiguity, for use in interactive or audit-log contexts.

    Parameters
    ----------
    slot:
        The ambiguous slot to format a question for.
    question_number:
        1-based position of this question in the current batch (default 1).
    total_questions:
        Total number of questions in the batch (default 1).

    Returns
    -------
    str
        A formatted multiple-choice question string.

    Raises
    ------
    ValueError
        If ``slot`` is not a DisagreementSlot, or ``question_number`` /
        ``total_questions`` are out of range.
    """
    if not isinstance(slot, DisagreementSlot):
        raise ValueError(
            f"slot must be a DisagreementSlot, got {type(slot).__name__}"
        )
    if question_number < 1:
        raise ValueError(f"question_number must be >= 1, got {question_number}")
    if total_questions < 1:
        raise ValueError(f"total_questions must be >= 1, got {total_questions}")
    if question_number > total_questions:
        raise ValueError(
            f"question_number ({question_number}) must not exceed "
            f"total_questions ({total_questions})"
        )

    unique_candidates = list(dict.fromkeys(slot.candidates))[:3]
    choices_text = "\n".join(
        f"  {i + 1}) {c}" for i, c in enumerate(unique_candidates)
    )
    if len(unique_candidates) < len(slot.candidates):
        choices_text += "\n  (other options omitted)"

    header = (
        f"[{question_number}/{total_questions}] [{slot.provenance}] "
        f"Ambiguous `{slot.dimension}` for `{slot.slot_name}` "
        f"(uncertainty={slot.uncertainty_score:.2f}):"
    )
    return (
        f"{header}\n"
        "  Which observable value is correct?\n"
        f"{choices_text}\n"
        f"  (provenance: {slot.provenance})"
    )


def ensure_boundary_and_error_coverage(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Guarantee the composite spec_quality_score's boundary_coverage and
    error_path_coverage sub-metrics are non-zero.

    The composite is a weighted geometric mean: a single zero sub-metric drives
    the composite to 0.0. This function ensures at least one boundary-condition
    AC and one error-path AC are present so the composite can exceed 0.0 and
    clear the 0.85 gate. Applied by both the LLM synthesis path and the
    deterministic fallback path so EITHER route yields gate-passing ACs.

    Parameters
    ----------
    criteria:
        List of AC strings to check and potentially augment.
    title:
        Feature title used to derive a filesystem-safe slug for injected ACs.

    Returns
    -------
    list[str]
        The original criteria, possibly with boundary and/or error-path ACs
        appended.

    Raises
    ------
    TypeError
        If ``criteria`` is not a list.
    """
    return _ensure_bec(criteria, title=title)


def deterministic_fallback(
    feature_name: str,
    feature_description: str = "",
    **kwargs: Any,
) -> list[str]:
    """Hardened deterministic fallback for failed LLM synthesis.

    Delegates to :func:`bob3.spec_synthesizer.deterministic_fallback` which
    holds the authoritative implementation. Both the LLM synthesis path and
    this fallback path apply :func:`ensure_boundary_and_error_coverage` so
    EITHER route yields gate-passing ACs (boundary_coverage and
    error_path_coverage are non-zero, preventing composite=0.0 from a
    weighted geometric mean with a zeroed sub-metric).

    Parameters
    ----------
    feature_name:
        Short feature name used to derive test file slugs. Must be a non-empty
        string with at least one non-stop-word token; raises ``ValueError``
        otherwise.
    feature_description:
        Feature description text (may be empty).
    **kwargs:
        Forward-compatible metadata (e.g. ``project_context``) accepted and
        silently ignored for API stability.

    Returns
    -------
    list[str]
        Machine-verifiable acceptance criteria including at least one
        boundary-condition AC and one error-path AC.

    Raises
    ------
    TypeError
        If ``feature_name`` is not a string.
    ValueError
        If ``feature_name`` is empty, whitespace-only, or composed entirely
        of stop-words.
    """
    return _deterministic_fallback(feature_name, feature_description, **kwargs)


def emit_plan_ready_event(
    feature_id: str,
    plan_path: str,
    approved: bool,
    workspace: Path | str | None = None,
) -> None:
    """Emit a PLAN_READY structured event to runs/events.jsonl.

    Called after the spec-critic (F-R7-450) passes and plan.yaml has been
    written, to signal that the plan is ready for implementer consideration.

    Parameters
    ----------
    feature_id:
        UUID of the feature.
    plan_path:
        Absolute path string of the written plan.yaml.
    approved:
        Whether plan.yaml is currently approved (True/False).
    workspace:
        Override for the workspace root (defaults to CWD).

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")

    from bob3.orchestrator.plan_gate import emit_plan_ready_event as _emit

    _emit(feature_id=feature_id, plan_path=plan_path, approved=approved, workspace=workspace)


def parse_property_ac(ac: str | None) -> PropertyAC | None:
    """Parse a ``property:`` acceptance criterion (seventh AC grammar).

    Grammar::

        property: <name> for <generator> assert <predicate>

    Delegates to :mod:`ac_grammar.property_based` which raises :exc:`ValueError`
    when the AC starts with ``property:`` but is malformed (missing ``for`` or
    ``assert`` clause).

    Parameters
    ----------
    ac:
        Raw AC string, or ``None`` (returns ``None`` immediately).

    Returns
    -------
    PropertyAC | None
        A parsed :class:`PropertyAC` when *ac* matches the grammar, ``None``
        when *ac* is not a property AC (e.g. ``pytest:`` or ``file exists:``).

    Raises
    ------
    ValueError
        When *ac* starts with ``property:`` but is malformed.
    """
    return _ac_parse_property_ac(ac)


def parse_key_example_ac(ac: dict | str | None) -> KeyExample | None:
    """Parse a ``key_example:`` sub-key entry from a behavior AC.

    Accepts two input forms:

    1. **Dict** with ``given`` and ``then`` keys::

           {"given": "x=5", "then": "result=25"}

    2. **String** in ``given: … then: …`` format::

           "given: x=5, then: result=25"

    Parameters
    ----------
    ac:
        Dict or string representation of a key-example entry.  ``None`` and
        empty strings/dicts return ``None`` without raising.

    Returns
    -------
    KeyExample | None
        A :class:`KeyExample` when *ac* contains the required fields, else
        ``None``.

    Raises
    ------
    ValueError
        When *ac* is a non-empty dict that is missing both ``given`` and
        ``then`` keys (i.e. clearly intended as a key-example but malformed).
    """
    return _ac_parse_key_example_ac(ac)


def validate_boundary_examples(
    ac: str,
    examples: list[KeyExample],
) -> BoundaryRequirement:
    """Validate that boundary key-examples are present when *ac* requires them.

    An AC requires boundary examples when it mentions data transformation or
    numeric range concepts (integers, floats, ranges, min/max, transforms,
    etc.).  When boundary examples are required but absent, the verifier flags
    the AC as a quality failure.

    Parameters
    ----------
    ac:
        Raw AC string to inspect.
    examples:
        Key-examples attached to this AC.

    Returns
    -------
    BoundaryRequirement
        A result object with ``required``, ``has_boundary``, and ``satisfied``
        properties.  ``satisfied`` is ``True`` when the requirement is met
        (either not required, or examples are present).

    Raises
    ------
    ValueError
        If *ac* is not a string.
    """
    if not isinstance(ac, str):
        raise ValueError(f"ac must be a string, got {type(ac).__name__}")
    return check_boundary_satisfied(ac, examples)


# ---------------------------------------------------------------------------
# N-sample stability check pre-critic (feature 9ad637e2)
# ---------------------------------------------------------------------------


def run_parallel_extraction(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
) -> Any:
    """Run the spec extractor N=3 times in parallel with different temperature/seeds.

    Delegates to :func:`spec_synthesizer.stability_check.run_parallel_extraction`.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings. Must be a list (may be empty).
    n:
        Number of parallel extractor samples (default 3). Must be a positive int.

    Returns
    -------
    StabilityResult
        Contains ``stability_score``, ``route``, ``consensus``,
        ``disagreeing_slots``, and ``majority_vote``.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    from spec_synthesizer.stability_check import run_parallel_extraction as _run

    return _run(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
    )


def normalize_variants(
    variants: list[list[dict[str, Any]]],
) -> list[frozenset[tuple[str, str]]]:
    """Normalize a list of AC variants into sets of (id, behavior) tuples.

    Each variant is a list of AC dicts. Normalization collapses whitespace in
    the ``behavior`` field and strips the ``id`` field for Jaccard comparison.

    Parameters
    ----------
    variants:
        List of AC variant specs. Each variant is a list of dicts with at
        least ``id`` and ``behavior`` keys.

    Returns
    -------
    list of frozenset of (id, behavior) tuples
        One frozenset per variant.

    Raises
    ------
    ValueError
        If ``variants`` is not a list or any element is not a list.
    """
    if not isinstance(variants, list):
        raise ValueError(
            f"variants must be a list, got {type(variants).__name__!r}"
        )
    from spec_synthesizer.stability_check import _normalize_variant

    normalized = []
    for i, v in enumerate(variants):
        if not isinstance(v, list):
            raise ValueError(
                f"Each variant must be a list of dicts; variants[{i}] is {type(v).__name__!r}"
            )
        normalized.append(_normalize_variant(v))
    return normalized


def compute_jaccard_stability(
    variants: list[list[dict[str, Any]]],
) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    For a single variant or empty-content variants the score is 1.0.
    For multiple variants: |intersection| / |union| of normalized AC sets.

    Parameters
    ----------
    variants:
        List of variant specs, each a list of AC dicts. Must be non-empty.

    Returns
    -------
    float
        Stability score in [0.0, 1.0].

    Raises
    ------
    ValueError
        If ``variants`` is empty or not a list of lists.
    """
    from spec_synthesizer.stability_check import compute_stability_score

    return compute_stability_score(variants)


def route_by_stability(
    score: float,
    variants: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    """Route a feature spec based on the Jaccard stability score.

    Routing table::

        score < 0.7   → route = "clarification"  (disagreeing slots cited)
        0.7 ≤ score < 0.9  → route = "critic"
        score ≥ 0.9   → route = "auto_accept"    (consensus: True)

    Parameters
    ----------
    score:
        Jaccard stability score in [0.0, 1.0].
    variants:
        AC variants used to compute the score (needed for majority vote and
        disagreeing-slots computation).

    Returns
    -------
    dict with keys:
        - ``route`` (str): one of ``"clarification"``, ``"critic"``, ``"auto_accept"``
        - ``consensus`` (bool): True when route == "auto_accept"
        - ``disagreeing_slots`` (list): (id, behavior) pairs that differ across variants
        - ``majority_vote`` (list): AC dicts from majority vote
        - ``stability_score`` (float): the input score

    Raises
    ------
    ValueError
        If ``score`` is not a float/int in [0.0, 1.0], or ``variants`` is not a list.
    """
    if not isinstance(score, (int, float)):
        raise ValueError(f"score must be a number, got {type(score).__name__!r}")
    if not 0.0 <= float(score) <= 1.0:
        raise ValueError(f"score must be in [0.0, 1.0], got {score!r}")
    if not isinstance(variants, list):
        raise ValueError(
            f"variants must be a list, got {type(variants).__name__!r}"
        )

    from spec_synthesizer.stability_check import (
        CLARIFICATION_THRESHOLD,
        AUTO_ACCEPT_THRESHOLD,
        _majority_vote,
        _disagreeing_slots,
    )

    score_f = float(score)
    n = len(variants)

    if score_f < CLARIFICATION_THRESHOLD:
        return {
            "route": "clarification",
            "consensus": False,
            "disagreeing_slots": _disagreeing_slots(variants),
            "majority_vote": _majority_vote(variants, n),
            "stability_score": score_f,
        }
    elif score_f >= AUTO_ACCEPT_THRESHOLD:
        return {
            "route": "auto_accept",
            "consensus": True,
            "disagreeing_slots": [],
            "majority_vote": _majority_vote(variants, n),
            "stability_score": score_f,
        }
    else:
        return {
            "route": "critic",
            "consensus": False,
            "disagreeing_slots": _disagreeing_slots(variants),
            "majority_vote": _majority_vote(variants, n),
            "stability_score": score_f,
        }


# ---------------------------------------------------------------------------
# Feature 968aead5: generate_candidates / compute_uncertainty / ask_for_clarification
# ---------------------------------------------------------------------------


def generate_candidates(
    acceptance_criteria: list[str],
    *,
    n_candidates: int = N_CANDIDATES,
) -> list[CandidateStub]:
    """Generate N candidate stub implementations from the draft spec.

    Alias for :func:`generate_candidate_implementations` with the public name
    required by feature 968aead5 AC-0.

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
        or ``n_candidates`` < 1.
    """
    return generate_candidate_implementations(
        acceptance_criteria, n_candidates=n_candidates
    )


def compute_uncertainty(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Alias for :func:`compute_disagreement_slots` with the public name required
    by feature 968aead5 AC-1.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidates`.
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
    return compute_disagreement_slots(stubs, threshold=threshold)


def ask_for_clarification(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = 5,
    ci_mode: bool | None = None,
    audit_log_path: Any = None,
) -> list[ClarificationAnswer] | str:
    """Trigger batched clarification questions for ambiguous slots.

    Alias matching the public name required by feature 968aead5 AC-2.
    Delegates to :func:`spec_synthesis.uncertainty_loop.trigger_clarification_questions`.

    In CI mode (no human present), raises :class:`SpecNeedsHumanError`
    when any disagreement slots are present.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When ``None``, reads ``BOB3_CI_MODE``.
    audit_log_path:
        Path to the clarifications audit log.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per disagreement slot (interactive mode), or empty list.

    Raises
    ------
    SpecNeedsHumanError
        When CI mode is active and ``disagreement_slots`` is non-empty.
    ValueError
        If ``disagreement_slots`` is not a list or ``max_per_round`` outside [1, 5].
    """
    from spec_synthesis.uncertainty_loop import (
        trigger_clarification_questions as _trigger,
    )

    return _trigger(
        disagreement_slots,
        max_per_round=max_per_round,
        ci_mode=ci_mode,
        audit_log_path=audit_log_path,
    )


def trigger_clarification_questions(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = 5,
    ci_mode: bool | None = None,
    audit_log_path: Any = None,
) -> list[ClarificationAnswer] | str:
    """Trigger batched clarification questions for ambiguous slots.

    Canonical public name required by feature 88a22cb9 AC-3.
    Alias for :func:`ask_for_clarification`.

    In CI mode (no human present), raises :class:`SpecNeedsHumanError`
    when any disagreement slots are present.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off. When ``None``, reads ``BOB3_CI_MODE``.
    audit_log_path:
        Path to the clarifications audit log.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per disagreement slot (interactive mode), or empty list.

    Raises
    ------
    SpecNeedsHumanError
        When CI mode is active and ``disagreement_slots`` is non-empty.
    ValueError
        If ``disagreement_slots`` is not a list or ``max_per_round`` outside [1, 5].
    """
    return ask_for_clarification(
        disagreement_slots,
        max_per_round=max_per_round,
        ci_mode=ci_mode,
        audit_log_path=audit_log_path,
    )
