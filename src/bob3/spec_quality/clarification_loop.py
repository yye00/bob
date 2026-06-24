"""Structured-uncertainty clarification loop (F-S5 / e38b904e).

Before finalising a feature spec, run a code-consistency check:

1. Generate N=3 candidate stub implementations from the draft spec.
2. If stubs disagree on observable behaviour (return-type signature,
   side-effect set, raised exceptions), mark the relevant slot ambiguous.
3. Compute a structured uncertainty score per slot (sample-disagreement
   rate over N stubs). Only slots above threshold T=0.4 trigger a question.
4. Questions are batched (1-5 per round) as multiple-choice (2-4
   candidates + "Other"), each citing the exact provenance span (F-R7-451)
   of the ambiguity.
5. Answers fold back into named slots (not freeform notes).
6. An audit trail ``clarifications.log`` records every interaction.
7. In CI mode (no human present), exit SPEC_NEEDS_HUMAN rather than
   confabulate.

Source: Agent 2 §F-S5 (ClarifyGPT + Ambig-SWE + Structured-Uncertainty +
AskUserQuestion), Agent 4 §ChatDev Communicative Dehallucination.

Public API::

    from bob3.spec_quality.clarification_loop import (
        code_consistency_check,
        compute_slot_uncertainty,
        ask_user_batched,
        fold_answer_into_slot,
    )
"""

from __future__ import annotations

import ast
import hashlib
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

UNCERTAINTY_THRESHOLD = 0.4  # slots above this trigger a question
N_STUBS = 3  # number of candidate stub implementations to generate
MAX_QUESTIONS_PER_ROUND = 5

SPEC_NEEDS_HUMAN = "SPEC_NEEDS_HUMAN"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CIClarificationRequiredError(RuntimeError):
    """Raised when CI mode is active, no human is present, and ambiguous slots exist."""

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SlotDescriptor:
    """A named observable slot extracted from a spec."""

    name: str  # e.g. "return_type", "raised_exceptions", "side_effects"
    provenance: str  # e.g. "F-R7-451" or AC index ref
    ac_text: str  # the AC text this slot was derived from


@dataclass
class CandidateStub:
    """One candidate stub implementation for a spec slot."""

    slot_name: str
    return_type: str  # observed return type annotation or "Any"
    raised_exceptions: list[str]  # list of exception type names
    side_effects: list[str]  # observable side-effect descriptions
    raw_stub: str  # the stub source text


@dataclass
class SlotUncertainty:
    """Uncertainty score and ambiguity details for one slot."""

    slot_name: str
    provenance: str
    uncertainty_score: float  # disagreement rate in [0, 1]
    candidates: list[str]  # concrete candidate values (for the question)
    dimension: str  # "return_type" | "raised_exceptions" | "side_effects"


@dataclass
class ClarificationQuestion:
    """A single multiple-choice question to resolve a slot ambiguity."""

    slot_name: str
    provenance: str
    question_text: str
    choices: list[str]  # 2-4 candidates + "Other"
    dimension: str


@dataclass
class ClarificationAnswer:
    """A resolved answer for one slot."""

    slot_name: str
    dimension: str
    selected: str  # the chosen value (may be "Other: <freeform>")
    timestamp: str  # ISO-8601


@dataclass
class ConsistencyReport:
    """Result of code_consistency_check."""

    stubs: list[CandidateStub]
    uncertain_slots: list[SlotUncertainty]
    spec_needs_human: bool = False  # set True when CI mode + ambiguity found


# ---------------------------------------------------------------------------
# Stub generation (synthetic — deterministic, no LLM required)
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
}


def _leading_verb(name: str) -> str:
    """Extract the leading verb from a function name like 'compute_score'."""
    return name.split("_")[0] if "_" in name else name[:6]


def _synthesise_stub(
    slot: SlotDescriptor,
    variant_idx: int,
) -> CandidateStub:
    """Deterministically generate one candidate stub for a slot."""
    verb = _leading_verb(slot.name)
    return_types = _RETURN_TYPE_VARIANTS.get(verb, ["Any", "None", "dict[str, Any]"])
    exception_sets = _EXCEPTION_VARIANTS.get(verb, [[], ["ValueError"], []])

    rt = return_types[variant_idx % len(return_types)]
    exc = exception_sets[variant_idx % len(exception_sets)]

    side_effects: list[str] = []
    if variant_idx == 0:
        side_effects = []
    elif variant_idx == 1:
        side_effects = ["writes_to_log"]
    else:
        side_effects = ["writes_to_log", "writes_to_file"]

    raw = textwrap.dedent(f"""\
        def {slot.name}(*args, **kwargs) -> {rt}:
            \"\"\"Stub variant {variant_idx}.\"\"\"
            {'raise ' + exc[0] + '()' if exc else 'return None'}
    """)

    return CandidateStub(
        slot_name=slot.name,
        return_type=rt,
        raised_exceptions=exc,
        side_effects=side_effects,
        raw_stub=raw,
    )


# ---------------------------------------------------------------------------
# Slot extraction from acceptance criteria
# ---------------------------------------------------------------------------

_FUNC_DEFINED_RE = re.compile(
    r"^Function\s+defined\s*:\s*([\w.]+)", re.IGNORECASE
)
_CLASS_DEFINED_RE = re.compile(
    r"^Class\s+defined\s*:\s*([\w.]+)", re.IGNORECASE
)


def _extract_slots(acceptance_criteria: list[str]) -> list[SlotDescriptor]:
    """Extract named observable slots from acceptance criteria."""
    slots: list[SlotDescriptor] = []
    for idx, ac in enumerate(acceptance_criteria):
        stripped = ac.strip()
        provenance = f"F-R7-{451 + idx}"

        m = _FUNC_DEFINED_RE.match(stripped)
        if m:
            full_name = m.group(1)
            func_name = full_name.split(".")[-1]
            slots.append(SlotDescriptor(
                name=func_name,
                provenance=provenance,
                ac_text=stripped,
            ))
            continue

        m = _CLASS_DEFINED_RE.match(stripped)
        if m:
            full_name = m.group(1)
            class_name = full_name.split(".")[-1]
            slots.append(SlotDescriptor(
                name=class_name,
                provenance=provenance,
                ac_text=stripped,
            ))

    return slots


# ---------------------------------------------------------------------------
# Public: code_consistency_check
# ---------------------------------------------------------------------------


def code_consistency_check(
    acceptance_criteria: list[str],
    *,
    n_stubs: int = N_STUBS,
    ci_mode: bool | None = None,
) -> ConsistencyReport:
    """Generate N candidate stubs and check for observable-behaviour disagreement.

    Parameters
    ----------
    acceptance_criteria:
        List of acceptance criterion strings for the feature.
    n_stubs:
        Number of candidate stubs to synthesise per slot (default 3).
    ci_mode:
        When True, CI mode is forced on. When None, the ``BOB3_CI_MODE``
        environment variable is consulted (any truthy value enables it).

    Returns
    -------
    ConsistencyReport
        Contains the generated stubs and a list of uncertain slots.
        ``spec_needs_human`` is True when CI mode is active and any slot
        exceeds the uncertainty threshold — the caller should surface this
        as SPEC_NEEDS_HUMAN instead of asking questions interactively.
    """
    if ci_mode is None:
        _ci_raw = os.environ.get("BOB3_CI_MODE", "").strip().lower()
        ci_mode = _ci_raw in ("1", "true", "yes", "on")

    slots = _extract_slots(acceptance_criteria)
    all_stubs: list[CandidateStub] = []
    uncertain_slots: list[SlotUncertainty] = []

    for slot in slots:
        stubs = [_synthesise_stub(slot, i) for i in range(n_stubs)]
        all_stubs.extend(stubs)

        # compute per-dimension uncertainty
        for dim, values in [
            ("return_type", [s.return_type for s in stubs]),
            ("raised_exceptions", [json.dumps(sorted(s.raised_exceptions)) for s in stubs]),
            ("side_effects", [json.dumps(sorted(s.side_effects)) for s in stubs]),
        ]:
            uncertainty = compute_slot_uncertainty(values)
            if uncertainty > UNCERTAINTY_THRESHOLD:
                candidates = sorted(set(values))
                uncertain_slots.append(SlotUncertainty(
                    slot_name=slot.name,
                    provenance=slot.provenance,
                    uncertainty_score=uncertainty,
                    candidates=candidates,
                    dimension=dim,
                ))
                logger.debug(
                    "Slot %s.%s uncertainty=%.2f (threshold=%.2f)",
                    slot.name, dim, uncertainty, UNCERTAINTY_THRESHOLD,
                )

    spec_needs_human = ci_mode and len(uncertain_slots) > 0

    if spec_needs_human:
        logger.info(
            "CI mode: %d uncertain slot(s) found — surfacing SPEC_NEEDS_HUMAN",
            len(uncertain_slots),
        )

    return ConsistencyReport(
        stubs=all_stubs,
        uncertain_slots=uncertain_slots,
        spec_needs_human=spec_needs_human,
    )


# ---------------------------------------------------------------------------
# Public: compute_slot_uncertainty
# ---------------------------------------------------------------------------


def compute_slot_uncertainty(values: list[str]) -> float:
    """Compute the disagreement rate for a list of observable values.

    The disagreement rate is (number of distinct values − 1) / (n − 1),
    clamped to [0, 1]. With n=3:
    - all same → 0.0
    - 2 distinct → 0.5
    - 3 distinct → 1.0

    Parameters
    ----------
    values:
        A list of string representations of the observable dimension
        (e.g. return-type annotations, JSON-serialised exception lists).

    Returns
    -------
    float
        Disagreement rate in [0, 1]. Returns 0.0 for empty or
        single-element lists.
    """
    if len(values) <= 1:
        return 0.0
    n_distinct = len(set(values))
    return (n_distinct - 1) / (len(values) - 1)


# ---------------------------------------------------------------------------
# Public: ask_user_batched
# ---------------------------------------------------------------------------


def ask_user_batched(
    uncertain_slots: list[SlotUncertainty],
    *,
    max_per_round: int = MAX_QUESTIONS_PER_ROUND,
    audit_log_path: Path | str | None = None,
) -> list[ClarificationAnswer]:
    """Present batched multiple-choice questions and collect answers.

    Questions are batched in rounds of at most ``max_per_round`` (1-5).
    Each question presents 2-4 candidate values plus an "Other" option,
    citing the provenance span of the ambiguity.

    In CI/automated mode (no TTY on stdin) this function falls back to
    selecting the first candidate for each slot rather than blocking.
    The audit log records this as ``"auto:<first_candidate>"``.

    Parameters
    ----------
    uncertain_slots:
        List of :class:`SlotUncertainty` objects whose scores exceed the
        threshold (as returned by :func:`code_consistency_check`).
    max_per_round:
        Maximum number of questions per interactive round (default 5).
    audit_log_path:
        Path to the ``clarifications.log`` audit trail. Defaults to
        ``clarifications.log`` in the current working directory.

    Returns
    -------
    list[ClarificationAnswer]
        One answer per uncertain slot, in the same order as input.
    """
    questions = _build_questions(uncertain_slots)
    answers: list[ClarificationAnswer] = []

    # Process in rounds of max_per_round
    for batch_start in range(0, len(questions), max_per_round):
        batch = questions[batch_start: batch_start + max_per_round]
        for q in batch:
            answer = _ask_one_question(q)
            answers.append(answer)

    _append_audit_log(questions, answers, audit_log_path=audit_log_path)
    return answers


def _build_questions(
    uncertain_slots: list[SlotUncertainty],
) -> list[ClarificationQuestion]:
    questions: list[ClarificationQuestion] = []
    for slot in uncertain_slots:
        # Trim to at most 3 unique candidates, then add "Other"
        unique_cands = list(dict.fromkeys(slot.candidates))[:3]
        choices = unique_cands + ["Other"]
        question_text = (
            f"[{slot.provenance}] Ambiguous {slot.dimension} for `{slot.slot_name}`:\n"
            f"  Which observable value is correct?"
        )
        questions.append(ClarificationQuestion(
            slot_name=slot.slot_name,
            provenance=slot.provenance,
            question_text=question_text,
            choices=choices,
            dimension=slot.dimension,
        ))
    return questions


def _ask_one_question(q: ClarificationQuestion) -> ClarificationAnswer:
    """Prompt interactively or auto-select in non-TTY environments."""
    ts = datetime.now(timezone.utc).isoformat()
    is_tty = os.isatty(0) if hasattr(os, "isatty") else False

    if not is_tty:
        selected = q.choices[0]
        logger.debug(
            "Non-TTY: auto-selecting %r for slot %s.%s",
            selected, q.slot_name, q.dimension,
        )
        return ClarificationAnswer(
            slot_name=q.slot_name,
            dimension=q.dimension,
            selected=f"auto:{selected}",
            timestamp=ts,
        )

    print(f"\n{q.question_text}")
    for i, choice in enumerate(q.choices, 1):
        print(f"  {i}) {choice}")
    print(f"  (provenance: {q.provenance})")

    while True:
        raw = input("  Select [1-{}]: ".format(len(q.choices))).strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(q.choices):
                selected = q.choices[idx]
                if selected == "Other":
                    freeform = input("  Describe the correct value: ").strip()
                    selected = f"Other: {freeform}"
                return ClarificationAnswer(
                    slot_name=q.slot_name,
                    dimension=q.dimension,
                    selected=selected,
                    timestamp=ts,
                )
        print("  Invalid selection — please enter a number between 1 and {}.".format(
            len(q.choices)
        ))


# ---------------------------------------------------------------------------
# Public: fold_answer_into_slot
# ---------------------------------------------------------------------------


def fold_answer_into_slot(
    spec_slots: dict[str, Any],
    answer: ClarificationAnswer,
) -> dict[str, Any]:
    """Fold a clarification answer back into a named slot dictionary.

    Answers are stored under ``<slot_name>.<dimension>`` rather than as
    freeform notes, preserving the structured shape of the spec for
    downstream consumers.

    Parameters
    ----------
    spec_slots:
        Mutable dictionary mapping slot names to their resolved values.
        Modified in-place and also returned for convenience.
    answer:
        A :class:`ClarificationAnswer` produced by :func:`ask_user_batched`.

    Returns
    -------
    dict[str, Any]
        The updated ``spec_slots`` dictionary.
    """
    slot_entry = spec_slots.setdefault(answer.slot_name, {})
    slot_entry[answer.dimension] = answer.selected
    slot_entry["_clarified_at"] = answer.timestamp
    return spec_slots


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

_DEFAULT_AUDIT_LOG_NAME = "clarifications.log"


def _audit_log_path(path: Path | str | None) -> Path:
    if path is not None:
        return Path(path)
    return Path.cwd() / _DEFAULT_AUDIT_LOG_NAME


def _append_audit_log(
    questions: list[ClarificationQuestion],
    answers: list[ClarificationAnswer],
    *,
    audit_log_path: Path | str | None = None,
) -> None:
    """Append one record per (question, answer) pair to the audit log."""
    log_path = _audit_log_path(audit_log_path)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            for q, a in zip(questions, answers):
                record = {
                    "timestamp": a.timestamp,
                    "slot_name": q.slot_name,
                    "dimension": q.dimension,
                    "provenance": q.provenance,
                    "question": q.question_text,
                    "choices": q.choices,
                    "selection": a.selected,
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("Failed to write clarification audit log to %s", log_path, exc_info=True)


# ---------------------------------------------------------------------------
# CI mode helper (exported for callers to surface SPEC_NEEDS_HUMAN)
# ---------------------------------------------------------------------------


def run_clarification_loop(
    acceptance_criteria: list[str],
    spec_slots: dict[str, Any] | None = None,
    *,
    n_stubs: int = N_STUBS,
    ci_mode: bool | None = None,
    audit_log_path: Path | str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """High-level orchestrator: check → question → fold.

    Runs the full clarification loop for a feature spec:
    1. ``code_consistency_check`` — generate stubs, compute uncertainty.
    2. If CI mode and uncertain slots → return SPEC_NEEDS_HUMAN.
    3. ``ask_user_batched`` — present questions interactively.
    4. ``fold_answer_into_slot`` — record answers into spec_slots.

    Parameters
    ----------
    acceptance_criteria:
        List of AC strings for the feature.
    spec_slots:
        Initial slot dictionary (may be empty). Modified in-place.
    n_stubs:
        Number of stubs to generate per slot (default 3).
    ci_mode:
        Force CI mode on/off; None reads BOB3_CI_MODE env var.
    audit_log_path:
        Path to the audit log; defaults to ``./clarifications.log``.

    Returns
    -------
    tuple[dict[str, Any], str | None]
        ``(spec_slots, SPEC_NEEDS_HUMAN)`` when CI mode blocks, or
        ``(spec_slots, None)`` when the loop completes successfully.
    """
    if spec_slots is None:
        spec_slots = {}

    report = code_consistency_check(
        acceptance_criteria, n_stubs=n_stubs, ci_mode=ci_mode
    )

    if report.spec_needs_human:
        return spec_slots, SPEC_NEEDS_HUMAN

    if not report.uncertain_slots:
        return spec_slots, None

    answers = ask_user_batched(
        report.uncertain_slots,
        audit_log_path=audit_log_path,
    )
    for answer in answers:
        fold_answer_into_slot(spec_slots, answer)

    return spec_slots, None


# ---------------------------------------------------------------------------
# Additional public helpers required by acceptance criteria
# ---------------------------------------------------------------------------


def uncertainty_threshold() -> float:
    """Return the configured uncertainty threshold (T=0.4).

    Slots whose disagreement rate exceeds this value trigger a clarification
    question (or SPEC_NEEDS_HUMAN in CI mode).
    """
    return UNCERTAINTY_THRESHOLD


def exit_spec_needs_human_in_ci(
    uncertain_slots: list[SlotUncertainty],
    *,
    ci_mode: bool | None = None,
) -> None:
    """Raise CIClarificationRequiredError when CI mode is active and slots are ambiguous.

    Parameters
    ----------
    uncertain_slots:
        List of slots whose uncertainty exceeds the threshold.
    ci_mode:
        Force CI mode; None reads BOB3_CI_MODE env var.

    Raises
    ------
    CIClarificationRequiredError
        When CI mode is active and ``uncertain_slots`` is non-empty.
    """
    if ci_mode is None:
        _ci_raw = os.environ.get("BOB3_CI_MODE", "").strip().lower()
        ci_mode = _ci_raw in ("1", "true", "yes", "on")

    if ci_mode and uncertain_slots:
        slot_names = ", ".join(f"{s.slot_name}.{s.dimension}" for s in uncertain_slots)
        raise CIClarificationRequiredError(
            f"CI mode: {len(uncertain_slots)} ambiguous slot(s) require human input "
            f"but no human is present — {SPEC_NEEDS_HUMAN}. "
            f"Ambiguous slots: {slot_names}"
        )


def handle_empty_slots(
    uncertain_slots: list[SlotUncertainty],
) -> list[ClarificationAnswer]:
    """Return an empty list when no slots exceed the uncertainty threshold.

    This is the zero/empty boundary handler: when ``uncertain_slots`` is
    empty (i.e. all slots are below T=0.4), there is nothing to ask, so
    ``ask_user_batched`` would be a no-op.  Callers can use this helper to
    make the short-circuit explicit and testable.

    Parameters
    ----------
    uncertain_slots:
        List of slots above the threshold (may be empty).

    Returns
    -------
    list[ClarificationAnswer]
        Always an empty list when ``uncertain_slots`` is empty; raises
        ``ValueError`` when called with a non-empty list (misuse guard).
    """
    if uncertain_slots:
        raise ValueError(
            "handle_empty_slots must only be called when uncertain_slots is empty; "
            f"got {len(uncertain_slots)} slot(s). Use ask_user_batched instead."
        )
    return []
