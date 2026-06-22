"""Structured-uncertainty clarification loop with AskUserQuestion (6dbc8bc6).

Generate N=3 candidate stub implementations from a draft spec; if the stubs
disagree on observable behaviour, mark the relevant slot ambiguous.  Slots
above uncertainty threshold T=0.4 trigger a batched (1-5 per round)
multiple-choice question citing provenance.  In CI mode with no human
present, exit SPEC_NEEDS_HUMAN rather than confabulate.

Public API::

    from spec_synthesis import (
        generate_candidate_stubs,
        compute_disagreement_slots,
        AskUserQuestion,
        exit_spec_needs_human,
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UNCERTAINTY_THRESHOLD = 0.4
N_CANDIDATES = 3
MAX_QUESTIONS_PER_ROUND = 5
SPEC_NEEDS_HUMAN = "SPEC_NEEDS_HUMAN"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SpecNeedsHumanError(RuntimeError):
    """Raised when CI mode is active and ambiguous slots exist."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SlotDescriptor:
    """A named observable slot extracted from a spec AC."""

    name: str
    provenance: str
    ac_text: str


@dataclass
class CandidateStub:
    """One candidate stub implementation for a spec slot."""

    slot_name: str
    return_type: str
    raised_exceptions: list[str]
    side_effects: list[str]
    raw_stub: str


@dataclass
class DisagreementSlot:
    """Aggregated disagreement info for one observable slot."""

    slot_name: str
    provenance: str
    uncertainty_score: float
    candidates: list[str]
    dimension: str


@dataclass
class ClarificationAnswer:
    """Resolved answer for one slot dimension."""

    slot_name: str
    dimension: str
    selected: str
    timestamp: str


# ---------------------------------------------------------------------------
# Stub-synthesis tables (deterministic — no LLM required)
# ---------------------------------------------------------------------------

_RETURN_TYPE_VARIANTS: dict[str, list[str]] = {
    "check": ["bool", "dict[str, Any]", "list[str]"],
    "compute": ["float", "dict[str, float]", "Any"],
    "get": ["str | None", "str", "Any"],
    "run": ["None", "int", "dict[str, Any]"],
    "parse": ["dict[str, Any]", "list[Any]", "Any"],
    "generate": ["list[str]", "str", "Any"],
    "validate": ["bool", "None", "tuple[bool, str]"],
    "ask": ["dict[str, str]", "list[ClarificationAnswer]", "None"],
    "fold": ["dict[str, Any]", "None", "Any"],
    "exit": ["None", "None", "None"],
}

_EXCEPTION_VARIANTS: dict[str, list[list[str]]] = {
    "check": [[], ["ValueError"], ["ValueError", "RuntimeError"]],
    "compute": [["ValueError"], [], ["TypeError"]],
    "get": [[], ["KeyError"], ["KeyError", "ValueError"]],
    "run": [["RuntimeError"], [], ["SystemExit"]],
    "parse": [["ValueError"], ["json.JSONDecodeError"], []],
    "generate": [[], ["NotImplementedError"], ["ValueError"]],
    "validate": [[], ["ValueError"], []],
    "ask": [[], ["RuntimeError"], []],
    "fold": [[], ["KeyError"], ["ValueError"]],
    "exit": [["SystemExit"], ["RuntimeError"], ["SystemExit"]],
}

_SIDE_EFFECT_VARIANTS: list[list[str]] = [
    [],
    ["writes_to_log"],
    ["writes_to_log", "writes_to_file"],
]


def _leading_verb(name: str) -> str:
    return name.split("_")[0] if "_" in name else name[:6]


# ---------------------------------------------------------------------------
# Slot extraction
# ---------------------------------------------------------------------------

_FUNC_DEF_RE = re.compile(r"^Function\s+defined\s*:\s*([\w.]+)", re.IGNORECASE)
_CLASS_DEF_RE = re.compile(r"^Class\s+defined\s*:\s*([\w.]+)", re.IGNORECASE)


def _extract_slots(acceptance_criteria: list[str]) -> list[SlotDescriptor]:
    slots: list[SlotDescriptor] = []
    for idx, ac in enumerate(acceptance_criteria):
        stripped = ac.strip()
        provenance = f"F-R7-{451 + idx}"
        m = _FUNC_DEF_RE.match(stripped) or _CLASS_DEF_RE.match(stripped)
        if m:
            short_name = m.group(1).split(".")[-1]
            slots.append(SlotDescriptor(
                name=short_name,
                provenance=provenance,
                ac_text=stripped,
            ))
    return slots


# ---------------------------------------------------------------------------
# Public: generate_candidate_stubs
# ---------------------------------------------------------------------------


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
    """
    slots = _extract_slots(acceptance_criteria)
    stubs: list[CandidateStub] = []
    for slot in slots:
        for i in range(n_candidates):
            verb = _leading_verb(slot.name)
            return_types = _RETURN_TYPE_VARIANTS.get(
                verb, ["Any", "None", "dict[str, Any]"]
            )
            exception_sets = _EXCEPTION_VARIANTS.get(
                verb, [[], ["ValueError"], []]
            )
            rt = return_types[i % len(return_types)]
            exc = exception_sets[i % len(exception_sets)]
            fx = _SIDE_EFFECT_VARIANTS[i % len(_SIDE_EFFECT_VARIANTS)]

            raw = textwrap.dedent(f"""\
                def {slot.name}(*args, **kwargs) -> {rt}:
                    \"\"\"Stub variant {i}.\"\"\"
                    {'raise ' + exc[0] + '()' if exc else 'return None'}
            """)
            stubs.append(CandidateStub(
                slot_name=slot.name,
                return_type=rt,
                raised_exceptions=exc,
                side_effects=fx,
                raw_stub=raw,
            ))
    return stubs


# ---------------------------------------------------------------------------
# Public: compute_disagreement_slots
# ---------------------------------------------------------------------------


def _disagreement_rate(values: list[str]) -> float:
    """(distinct − 1) / (n − 1), clamped to [0, 1]."""
    if len(values) <= 1:
        return 0.0
    return (len(set(values)) - 1) / (len(values) - 1)


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
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4).

    Returns
    -------
    list[DisagreementSlot]
        Slots whose disagreement rate is above ``threshold``, sorted by
        slot name and dimension for deterministic ordering.
    """
    # Group by slot_name, preserving insertion order for provenance
    by_slot: dict[str, list[CandidateStub]] = {}
    for s in stubs:
        by_slot.setdefault(s.slot_name, []).append(s)

    result: list[DisagreementSlot] = []
    for slot_name, slot_stubs in by_slot.items():
        # Use provenance placeholder (callers may inject real provenance)
        provenance = f"F-R7-{hash(slot_name) % 1000 + 451}"

        for dim, values in [
            ("return_type", [s.return_type for s in slot_stubs]),
            (
                "raised_exceptions",
                [json.dumps(sorted(s.raised_exceptions)) for s in slot_stubs],
            ),
            (
                "side_effects",
                [json.dumps(sorted(s.side_effects)) for s in slot_stubs],
            ),
        ]:
            score = _disagreement_rate(values)
            if score > threshold:
                result.append(DisagreementSlot(
                    slot_name=slot_name,
                    provenance=provenance,
                    uncertainty_score=score,
                    candidates=sorted(set(values)),
                    dimension=dim,
                ))
                logger.debug(
                    "Slot %s.%s disagreement=%.2f (threshold=%.2f)",
                    slot_name, dim, score, threshold,
                )

    result.sort(key=lambda s: (s.slot_name, s.dimension))
    return result


# ---------------------------------------------------------------------------
# Public: AskUserQuestion
# ---------------------------------------------------------------------------


def AskUserQuestion(
    disagreement_slots: list[DisagreementSlot],
    *,
    max_per_round: int = MAX_QUESTIONS_PER_ROUND,
    audit_log_path: Path | str | None = None,
) -> list[ClarificationAnswer]:
    """Present batched multiple-choice questions and collect answers.

    Questions are batched in rounds of at most ``max_per_round`` (1-5),
    each citing the provenance span of the ambiguity.  In non-TTY
    environments (CI) the first candidate is auto-selected and the
    selection is recorded as ``"auto:<value>"`` in the audit log.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold, as returned by
        :func:`compute_disagreement_slots`.
    max_per_round:
        Maximum questions per interactive round (default 5).
    audit_log_path:
        Path to the ``clarifications.log`` audit trail.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per disagreement slot.
    """
    answers: list[ClarificationAnswer] = []
    is_tty = os.isatty(0) if hasattr(os, "isatty") else False

    for batch_start in range(0, len(disagreement_slots), max_per_round):
        batch = disagreement_slots[batch_start: batch_start + max_per_round]
        for slot in batch:
            ts = datetime.now(timezone.utc).isoformat()
            unique_cands = list(dict.fromkeys(slot.candidates))[:3]
            choices = unique_cands + ["Other"]

            if not is_tty:
                selected = f"auto:{choices[0]}"
                logger.debug(
                    "Non-TTY: auto-selecting %r for slot %s.%s",
                    selected, slot.slot_name, slot.dimension,
                )
                answers.append(ClarificationAnswer(
                    slot_name=slot.slot_name,
                    dimension=slot.dimension,
                    selected=selected,
                    timestamp=ts,
                ))
                continue

            # Interactive path
            print(
                f"\n[{slot.provenance}] Ambiguous {slot.dimension} for "
                f"`{slot.slot_name}` (uncertainty={slot.uncertainty_score:.2f}):\n"
                "  Which observable value is correct?"
            )
            for i, choice in enumerate(choices, 1):
                print(f"  {i}) {choice}")
            print(f"  (provenance: {slot.provenance})")

            while True:
                raw = input(f"  Select [1-{len(choices)}]: ").strip()
                if raw.isdigit():
                    idx = int(raw) - 1
                    if 0 <= idx < len(choices):
                        selected = choices[idx]
                        if selected == "Other":
                            freeform = input("  Describe the correct value: ").strip()
                            selected = f"Other: {freeform}"
                        answers.append(ClarificationAnswer(
                            slot_name=slot.slot_name,
                            dimension=slot.dimension,
                            selected=selected,
                            timestamp=ts,
                        ))
                        break
                print(f"  Invalid — enter a number between 1 and {len(choices)}.")

    _append_audit_log(disagreement_slots, answers, audit_log_path=audit_log_path)
    return answers


def _append_audit_log(
    slots: list[DisagreementSlot],
    answers: list[ClarificationAnswer],
    *,
    audit_log_path: Path | str | None = None,
) -> None:
    log_path = Path(audit_log_path) if audit_log_path else Path.cwd() / "clarifications.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            for slot, answer in zip(slots, answers):
                record = {
                    "timestamp": answer.timestamp,
                    "slot_name": slot.slot_name,
                    "dimension": slot.dimension,
                    "provenance": slot.provenance,
                    "uncertainty_score": slot.uncertainty_score,
                    "candidates": slot.candidates,
                    "selection": answer.selected,
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning(
            "Failed to write clarification audit log to %s", log_path, exc_info=True
        )


# ---------------------------------------------------------------------------
# Public: exit_spec_needs_human
# ---------------------------------------------------------------------------


def exit_spec_needs_human(
    disagreement_slots: list[DisagreementSlot],
    *,
    ci_mode: bool | None = None,
) -> str:
    """Exit with SPEC_NEEDS_HUMAN when CI mode is active and slots are ambiguous.

    In CI mode (no human present), we must never confabulate an answer.
    This function raises :class:`SpecNeedsHumanError` (which callers
    should surface as the ``SPEC_NEEDS_HUMAN`` sentinel) whenever ambiguous
    slots are found and CI mode is enabled.

    Parameters
    ----------
    disagreement_slots:
        Slots above the uncertainty threshold from
        :func:`compute_disagreement_slots`.
    ci_mode:
        Force CI mode on/off; ``None`` reads the ``BOB3_CI_MODE``
        environment variable.

    Returns
    -------
    str
        ``SPEC_NEEDS_HUMAN`` constant when called programmatically
        without raising (only possible when ``disagreement_slots`` is
        empty or CI mode is off).

    Raises
    ------
    SpecNeedsHumanError
        When CI mode is active and ``disagreement_slots`` is non-empty.
    """
    if ci_mode is None:
        _raw = os.environ.get("BOB3_CI_MODE", "").strip().lower()
        ci_mode = _raw in ("1", "true", "yes", "on")

    if ci_mode and disagreement_slots:
        slot_names = ", ".join(
            f"{s.slot_name}.{s.dimension}" for s in disagreement_slots
        )
        raise SpecNeedsHumanError(
            f"CI mode: {len(disagreement_slots)} ambiguous slot(s) require "
            f"human input but no human is present — {SPEC_NEEDS_HUMAN}. "
            f"Slots: {slot_names}"
        )

    return SPEC_NEEDS_HUMAN


# ---------------------------------------------------------------------------
# High-level orchestrator
# ---------------------------------------------------------------------------


def run_clarification_loop(
    acceptance_criteria: list[str],
    spec_slots: dict[str, Any] | None = None,
    *,
    n_candidates: int = N_CANDIDATES,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Full clarification loop: generate → check → ask → fold.

    1. ``generate_candidate_stubs`` — produce N stubs per slot.
    2. ``compute_disagreement_slots`` — find slots above T=0.4.
    3. If CI mode and any disagreement → return ``SPEC_NEEDS_HUMAN``.
    4. ``AskUserQuestion`` — collect answers interactively.
    5. Fold answers back into ``spec_slots``.

    Returns
    -------
    tuple[dict[str, Any], str | None]
        ``(spec_slots, SPEC_NEEDS_HUMAN)`` when blocked, or
        ``(spec_slots, None)`` when complete.
    """
    if spec_slots is None:
        spec_slots = {}

    stubs = generate_candidate_stubs(acceptance_criteria, n_candidates=n_candidates)
    disagreements = compute_disagreement_slots(stubs)

    # CI gate
    if ci_mode is None:
        _raw = os.environ.get("BOB3_CI_MODE", "").strip().lower()
        _ci = _raw in ("1", "true", "yes", "on")
    else:
        _ci = ci_mode

    if _ci and disagreements:
        return spec_slots, SPEC_NEEDS_HUMAN

    if not disagreements:
        return spec_slots, None

    answers = AskUserQuestion(
        disagreements,
        audit_log_path=audit_log_path,
    )
    for answer in answers:
        slot_entry = spec_slots.setdefault(answer.slot_name, {})
        slot_entry[answer.dimension] = answer.selected
        slot_entry["_clarified_at"] = answer.timestamp

    return spec_slots, None


# ---------------------------------------------------------------------------
# Public: mark_ambiguous_slots
# ---------------------------------------------------------------------------


def mark_ambiguous_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[DisagreementSlot]:
    """Mark slots as ambiguous when candidate stubs disagree on observable behaviour.

    A named alias for :func:`compute_disagreement_slots` using the
    feature-specification vocabulary ("mark ambiguous"). Slots whose
    disagreement rate exceeds ``threshold`` are returned and can be fed
    directly to :func:`clarify_with_questions`.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4).

    Returns
    -------
    list[DisagreementSlot]
        Slots above the uncertainty threshold, sorted by slot name and
        dimension for deterministic ordering.

    Raises
    ------
    ValueError
        If ``stubs`` is not a list or ``threshold`` is outside [0, 1].
    """
    if not isinstance(stubs, list):
        raise ValueError(f"stubs must be a list, got {type(stubs).__name__}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    return compute_disagreement_slots(stubs, threshold=threshold)


# ---------------------------------------------------------------------------
# Public: clarify_with_questions
# ---------------------------------------------------------------------------


def clarify_with_questions(
    acceptance_criteria: list[str],
    spec_slots: dict[str, Any] | None = None,
    *,
    n_candidates: int = N_CANDIDATES,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Structured-uncertainty clarification loop with AskUserQuestion.

    Generates N=3 candidate stub implementations from the draft spec; if
    stubs disagree on observable behaviour, marks the relevant slot ambiguous.
    Slots above uncertainty threshold T=0.4 trigger batched (1-5 per round)
    multiple-choice questions citing provenance.  In CI mode with no human
    present, returns ``SPEC_NEEDS_HUMAN`` rather than confabulate.

    Orchestrates:
    1. :func:`generate_candidate_stubs` — produce N stubs per slot.
    2. :func:`mark_ambiguous_slots` — find slots above T=0.4.
    3. If CI mode and any disagreement → return ``SPEC_NEEDS_HUMAN``.
    4. :func:`AskUserQuestion` — collect answers interactively.
    5. Fold answers back into ``spec_slots``.

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
        Force CI mode on/off; ``None`` reads the ``BOB3_CI_MODE``
        environment variable.
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

    return run_clarification_loop(
        acceptance_criteria,
        spec_slots,
        n_candidates=n_candidates,
        ci_mode=ci_mode,
        audit_log_path=audit_log_path,
    )
