"""Structured-uncertainty clarification loop with AskUserQuestion.

Generate N=3 candidate stub implementations from the draft spec;
if they disagree on observable behaviour, mark the relevant slot
ambiguous. Slots above uncertainty threshold T=0.4 trigger a
batched (1-5 per round) multiple-choice question citing provenance.
In CI mode with no human present, exit SPEC_NEEDS_HUMAN rather than
confabulate.

Public API::

    from bob3.structured_uncertainty_loop import (
        generate_candidate_stubs,
        compute_uncertainty_slots,
        batch_clarification_questions,
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
N_STUBS = 3
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
class UncertaintySlot:
    """Uncertainty score and ambiguity details for one slot."""

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
# Stub synthesis tables (deterministic — no LLM required)
# ---------------------------------------------------------------------------

_RETURN_TYPE_VARIANTS: dict[str, list[str]] = {
    "check": ["bool", "dict[str, Any]", "list[str]"],
    "compute": ["float", "dict[str, float]", "Any"],
    "get": ["str | None", "str", "Any"],
    "run": ["None", "int", "dict[str, Any]"],
    "parse": ["dict[str, Any]", "list[Any]", "Any"],
    "generate": ["list[str]", "str", "Any"],
    "validate": ["bool", "None", "tuple[bool, str]"],
    "ask": ["dict[str, str]", "list[str]", "None"],
    "fold": ["dict[str, Any]", "None", "Any"],
    "batch": ["list[str]", "dict[str, Any]", "None"],
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
    "batch": [[], ["ValueError"], []],
}

_SIDE_EFFECT_VARIANTS: list[list[str]] = [
    [],
    ["writes_to_log"],
    ["writes_to_log", "writes_to_file"],
]


def _leading_verb(name: str) -> str:
    """Extract the leading verb from a function name."""
    return name.split("_")[0] if "_" in name else name[:6]


# ---------------------------------------------------------------------------
# Slot extraction from acceptance criteria
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


def _synthesise_stub(slot: SlotDescriptor, variant_idx: int) -> CandidateStub:
    """Deterministically generate one candidate stub for a slot."""
    verb = _leading_verb(slot.name)
    return_types = _RETURN_TYPE_VARIANTS.get(verb, ["Any", "None", "dict[str, Any]"])
    exception_sets = _EXCEPTION_VARIANTS.get(verb, [[], ["ValueError"], []])

    rt = return_types[variant_idx % len(return_types)]
    exc = exception_sets[variant_idx % len(exception_sets)]
    fx = _SIDE_EFFECT_VARIANTS[variant_idx % len(_SIDE_EFFECT_VARIANTS)]

    raw = textwrap.dedent(f"""\
        def {slot.name}(*args, **kwargs) -> {rt}:
            \"\"\"Stub variant {variant_idx}.\"\"\"
            {'raise ' + exc[0] + '()' if exc else 'return None'}
    """)

    return CandidateStub(
        slot_name=slot.name,
        return_type=rt,
        raised_exceptions=exc,
        side_effects=fx,
        raw_stub=raw,
    )


# ---------------------------------------------------------------------------
# Public: generate_candidate_stubs
# ---------------------------------------------------------------------------


def generate_candidate_stubs(
    acceptance_criteria: list[str],
    *,
    n_stubs: int = N_STUBS,
) -> list[CandidateStub]:
    """Generate N candidate stub implementations from the draft spec.

    For each "Function defined" or "Class defined" AC, produce ``n_stubs``
    stubs that vary in return type, raised exceptions, and side effects. If
    stubs disagree on observable behaviour the relevant slot is considered
    ambiguous.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature.
    n_stubs:
        Number of candidate stubs to generate per slot (default 3).

    Returns
    -------
    list[CandidateStub]
        All generated stubs (``n_stubs`` × number of extracted slots).

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, contains non-strings, or
        ``n_stubs`` is less than 1.
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
    if n_stubs < 1:
        raise ValueError(f"n_stubs must be >= 1, got {n_stubs}")

    slots = _extract_slots(acceptance_criteria)
    stubs: list[CandidateStub] = []
    for slot in slots:
        for i in range(n_stubs):
            stubs.append(_synthesise_stub(slot, i))
    return stubs


# ---------------------------------------------------------------------------
# Public: compute_uncertainty_slots
# ---------------------------------------------------------------------------


def _disagreement_rate(values: list[str]) -> float:
    """(distinct − 1) / (n − 1), clamped to [0, 1]."""
    if len(values) <= 1:
        return 0.0
    return (len(set(values)) - 1) / (len(values) - 1)


def compute_uncertainty_slots(
    stubs: list[CandidateStub],
    *,
    threshold: float = UNCERTAINTY_THRESHOLD,
) -> list[UncertaintySlot]:
    """Identify slots where candidate stubs disagree on observable behaviour.

    Groups ``stubs`` by ``slot_name``, then computes a disagreement rate for
    each observable dimension (return type, raised exceptions, side effects).
    Slots whose rate exceeds ``threshold`` are returned.

    Parameters
    ----------
    stubs:
        Candidate stubs produced by :func:`generate_candidate_stubs`.
    threshold:
        Uncertainty threshold (default T=0.4). Must be in [0, 1].

    Returns
    -------
    list[UncertaintySlot]
        Slots whose disagreement rate is above ``threshold``, sorted by slot
        name and dimension for deterministic ordering.

    Raises
    ------
    ValueError
        If ``stubs`` is not a list or ``threshold`` is outside [0, 1].
    """
    if not isinstance(stubs, list):
        raise ValueError(f"stubs must be a list, got {type(stubs).__name__}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")

    by_slot: dict[str, list[CandidateStub]] = {}
    for s in stubs:
        by_slot.setdefault(s.slot_name, []).append(s)

    result: list[UncertaintySlot] = []
    for slot_name, slot_stubs in by_slot.items():
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
                result.append(UncertaintySlot(
                    slot_name=slot_name,
                    provenance=provenance,
                    uncertainty_score=score,
                    candidates=sorted(set(values)),
                    dimension=dim,
                ))
                logger.debug(
                    "Slot %s.%s uncertainty=%.2f (threshold=%.2f)",
                    slot_name, dim, score, threshold,
                )

    result.sort(key=lambda s: (s.slot_name, s.dimension))
    return result


# ---------------------------------------------------------------------------
# Public: batch_clarification_questions
# ---------------------------------------------------------------------------


def batch_clarification_questions(
    uncertain_slots: list[UncertaintySlot],
    *,
    max_per_round: int = MAX_QUESTIONS_PER_ROUND,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> list[ClarificationAnswer]:
    """Present batched multiple-choice questions and collect answers.

    Questions are batched in rounds of at most ``max_per_round`` (1-5),
    each citing the provenance span of the ambiguity. In CI mode (no human
    present), raises :class:`SpecNeedsHumanError` with the SPEC_NEEDS_HUMAN
    sentinel rather than confabulating answers.

    Parameters
    ----------
    uncertain_slots:
        Slots above the uncertainty threshold, as returned by
        :func:`compute_uncertainty_slots`.
    max_per_round:
        Maximum questions per interactive round (1-5, default 5).
    ci_mode:
        Force CI mode on/off; ``None`` reads the ``BOB3_CI_MODE``
        environment variable.
    audit_log_path:
        Path to the ``clarifications.log`` audit trail.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per uncertain slot (auto-selected in non-TTY environments).

    Raises
    ------
    ValueError
        If ``uncertain_slots`` is not a list or ``max_per_round`` is outside
        [1, 5].
    SpecNeedsHumanError
        When CI mode is active and ``uncertain_slots`` is non-empty.
    """
    if not isinstance(uncertain_slots, list):
        raise ValueError(
            f"uncertain_slots must be a list, got {type(uncertain_slots).__name__}"
        )
    if not 1 <= max_per_round <= 5:
        raise ValueError(
            f"max_per_round must be in [1, 5], got {max_per_round}"
        )

    # Resolve CI mode
    if ci_mode is None:
        _raw = os.environ.get("BOB3_CI_MODE", "").strip().lower()
        ci_mode = _raw in ("1", "true", "yes", "on")

    if ci_mode and uncertain_slots:
        slot_names = ", ".join(
            f"{s.slot_name}.{s.dimension}" for s in uncertain_slots
        )
        raise SpecNeedsHumanError(
            f"CI mode: {len(uncertain_slots)} ambiguous slot(s) require "
            f"human input but no human is present — {SPEC_NEEDS_HUMAN}. "
            f"Slots: {slot_names}"
        )

    answers: list[ClarificationAnswer] = []
    is_tty = os.isatty(0) if hasattr(os, "isatty") else False

    for batch_start in range(0, len(uncertain_slots), max_per_round):
        batch = uncertain_slots[batch_start: batch_start + max_per_round]
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

            # Interactive path (TTY)
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

    _append_audit_log(uncertain_slots, answers, audit_log_path=audit_log_path)
    return answers


def _append_audit_log(
    slots: list[UncertaintySlot],
    answers: list[ClarificationAnswer],
    *,
    audit_log_path: Path | str | None = None,
) -> None:
    log_path = (
        Path(audit_log_path) if audit_log_path else Path.cwd() / "clarifications.log"
    )
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
