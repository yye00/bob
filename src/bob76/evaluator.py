"""bob76.evaluator — Evaluator integration for structured EARS-style behavior ACs.

Augments the evaluator prompt with structured checks derived from the parsed
:class:`~bob76.ears.BehaviorCriterion` tuple, so the grader verifies each
subject-verb-object-condition tuple explicitly rather than relying on freeform
prose in the description.

Public API
----------
build_behavior_check(criterion) -> str
    Build a structured grading prompt fragment for a single parsed
    :class:`~bob76.ears.BehaviorCriterion`.
build_evaluator_section(criteria) -> str
    Build the full evaluator section for all behavior ACs in *criteria*.
"""

from __future__ import annotations

from bob76.ears import BehaviorCriterion, parse_behavior_criterion


def build_behavior_check(criterion: BehaviorCriterion) -> str:
    """Build a structured grading prompt fragment for a parsed behavior AC.

    The returned string instructs the independent grader to verify the exact
    subject-verb-object under the exact condition using parsed structure.

    Args:
        criterion: A parsed :class:`~bob76.ears.BehaviorCriterion`.

    Returns:
        A multi-line string with a structured grading question.
    """
    subject = criterion.subject or "(unspecified subject)"
    verb = criterion.verb or "(unspecified verb)"
    obj = criterion.object_ or "(unspecified object)"
    condition = criterion.condition

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


def build_evaluator_section(criteria: str | list[str]) -> str:
    """Build the evaluator section for all behavior ACs in *criteria*.

    Parses *criteria* for ``behavior:`` entries and produces a structured
    verification section using the parsed (subject, verb, object_, condition)
    tuple. Returns an empty string when no behavior ACs are present.

    Args:
        criteria: Raw acceptance criteria text or list of AC strings.

    Returns:
        A string to append to the evaluator prompt, or ``""`` if there are
        no behavior ACs.
    """
    import json

    items: list[str] = []
    if isinstance(criteria, list):
        items = criteria
    elif isinstance(criteria, str):
        stripped = criteria.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    items = [str(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        if not items:
            items = [line.strip() for line in stripped.splitlines() if line.strip()]

    behavior_criteria: list[BehaviorCriterion] = []
    for item in items:
        try:
            bc = parse_behavior_criterion(item)
            if bc is not None:
                behavior_criteria.append(bc)
        except ValueError:
            pass

    if not behavior_criteria:
        return ""

    parts = [
        "\n## Structured behavior-AC checks\n\n"
        "For each behavior criterion below, follow the structured verification "
        "steps exactly — use the parsed (subject, verb, object, condition) "
        "structure rather than consulting the freeform description.\n"
    ]
    for i, bc in enumerate(behavior_criteria, start=1):
        parts.append(f"\n**Behavior AC {i}:** `{bc.subject} {bc.verb} {bc.object_} when {bc.condition}`\n\n")
        parts.append(build_behavior_check(bc))
        parts.append("\n")

    return "".join(parts)


__all__ = ["build_behavior_check", "build_evaluator_section"]
