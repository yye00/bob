"""Bob3 evaluator integration module.

Augments the independent evaluator's prompt with structured EARS-style
behavior AC checks so the grader verifies each subject-verb-object-condition
tuple explicitly rather than relying on freeform prose in the description.

The main entry point is :func:`build_evaluator_task_section`, which takes
raw acceptance criteria and returns the ``## Your task`` section for the
evaluator prompt, with structured behavior AC checks appended when present.

Also re-exports the spec_quality_allowlist helpers so evaluator callers can
skip the quality gate for permanent forward-carry infra features without an
additional import.
"""

from __future__ import annotations

from bob3.spec_quality.ears_parser import (
    BehaviorAC,
    behavior_acs_from_criteria,
    build_behavior_ac_evaluator_section,
    evaluate_behavior_ac,
    parse_behavior_ac,
)
from bob3.spec_quality_allowlist import is_permanent_forward_carry, load_allowlist_patterns
from bob3.sticky_completed import (
    should_reset_completion_stamp,
    prevent_status_downgrade,
    is_completion_persisted,
)
from bob3.sticky_completed_gate import check_sticky_completed, reset_completion_stamp
from bob3.ears_parser import BehaviorTuple, parse_behavior_criterion
from bob3.test_ownership_map import build_test_ownership_map, verify_regression_owner
from bob3.pending_successor_detector import (
    detect_pending_successor_verify,
    scan_acs_for_verification_tokens,
    should_defer_to_successor,
)

__all__ = [
    "BehaviorAC",
    "BehaviorTuple",
    "behavior_acs_from_criteria",
    "build_behavior_ac_evaluator_section",
    "check_behavior_criterion",
    "evaluate_behavior_ac",
    "parse_behavior_ac",
    "parse_behavior_criterion",
    "build_evaluator_task_section",
    "is_permanent_forward_carry",
    "load_allowlist_patterns",
    "should_reset_completion_stamp",
    "prevent_status_downgrade",
    "is_completion_persisted",
    "check_sticky_completed",
    "reset_completion_stamp",
    "sticky_completed_gate",
    "build_test_ownership_map",
    "verify_regression_owner",
    "detect_pending_successor_verify",
    "scan_acs_for_verification_tokens",
    "should_defer_to_successor",
]

_BASE_TASK_SECTION = (
    "1. Identify each acceptance criterion.\n"
    "2. For each criterion, decide whether the diff satisfies it. "
    "Use the Read/Grep/Bash tools to verify in context (run pytest, "
    "look at the actual files, etc.). Do NOT edit anything.\n"
    "3. Apply the adversarial-self-review checklist if installed in "
    "your workspace at .claude/skills/adversarial-self-review/.\n"
    "4. Return a single JSON object inside a ```json fence with the "
    "fields described in your system prompt: "
    "verdict, findings, confidence, evidence.\n"
)


def build_evaluator_task_section(acceptance_criteria: str | list[str]) -> str:
    """Build the ``## Your task`` body for an evaluator prompt.

    Appends structured EARS behavior-AC checks when *acceptance_criteria*
    contains any ``behavior: <subject> <verb> <object> when <condition>``
    entries.  Returns the plain base section when no behavior ACs are present,
    preserving backward compatibility.

    Args:
        acceptance_criteria: Raw AC string (JSON list or newline-separated)
            or a Python list of AC strings.

    Returns:
        A string suitable for use as the evaluator prompt's ``## Your task``
        body (without the ``## Your task`` header itself).
    """
    behavior_section = build_behavior_ac_evaluator_section(acceptance_criteria)
    return _BASE_TASK_SECTION + behavior_section


def check_behavior_criterion(ac: str) -> str | None:
    """Check a behavior AC using its parsed structured tuple.

    Parses *ac* with :func:`parse_behavior_criterion` and returns a structured
    verification prompt string that instructs the evaluator to check the
    subject-verb-object-condition tuple explicitly, rather than relying on
    freeform prose.

    Returns ``None`` for non-behavior ACs (those that don't start with
    ``behavior:``).  Raises ``ValueError`` for malformed behavior ACs (prefix
    present but ``when`` clause missing).

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        A structured verification prompt string when *ac* is a valid behavior
        AC; ``None`` when *ac* is not a behavior AC.

    Raises:
        ValueError: When *ac* starts with ``behavior:`` but lacks a ``when``
            clause or cannot be parsed.
    """
    bt = parse_behavior_criterion(ac)
    if bt is None:
        return None

    subject = bt.subject or "(unspecified subject)"
    verb = bt.verb or "(unspecified verb)"
    obj = bt.object_ or "(unspecified object)"
    condition = bt.condition

    return (
        "### Behavior AC check\n"
        f"Does **{subject}** **{verb}** **{obj}** when **{condition}**?\n\n"
        "Verify each part specifically:\n"
        f"- Subject `{subject}`: identify the code entity responsible for this action.\n"
        f"- Verb `{verb}`: confirm the action is actually performed (not mocked, stubbed, or no-op).\n"
        f"- Object `{obj}`: confirm the target entity is affected, produced, or returned.\n"
        f"- Condition `when {condition}`: confirm the behavior is triggered only/specifically under this condition.\n\n"
        "Answer YES/NO for each part above, then give an overall PASS or FAIL "
        "for this criterion with a one-sentence rationale and a `file:line` reference."
    )


def sticky_completed_gate(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: "str | list[str] | None",
    workspace: "pathlib.Path | str | None" = None,
) -> bool:
    """Evaluator integration point for the sticky-completed gate.

    Call this before applying any evaluator-FAIL or regression-cascade vote
    that would demote a feature's status.  Returns True when the demotion is
    BLOCKED (feature was completed in the parent generation and its AC files
    still verify on disk); returns False when demotion may proceed.

    This is a thin wrapper around :func:`check_sticky_completed` exposed
    directly on the evaluator module so callers can import it from
    ``bob3.evaluator`` without an additional hop.

    Args:
        parent_completed: True when the feature was status='completed' in
            the parent generation's DB.
        target_status: The status the caller wishes to assign.
        acceptance_criteria: Raw JSON string or Python list of AC strings.
            May be None or empty — treated as an empty list.
        workspace: Root directory for disk-based AC verification. Defaults
            to ``pathlib.Path.cwd()``.

    Returns:
        True  — demotion is BLOCKED; keep the feature at 'ready'.
        False — demotion may proceed.

    Raises:
        ValueError: If *parent_completed* is not a bool, *target_status* is
            not a non-empty string, or *workspace* exists but is not a
            directory.
    """
    import pathlib as _pathlib

    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
