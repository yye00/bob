"""EARS-style behavior acceptance criteria parser for bob.

Provides the sixth AC grammar:

    behavior: <subject> <verb> <object> when <condition>

At load time, ``parse_behavior_criterion`` parses the AC string into a
structured :class:`EARSBehavior` tuple. The evaluator uses those discrete
fields to produce a targeted verification prompt rather than relying on
freeform prose.

Public API
----------
EARSBehavior
    Named-tuple (subject, verb, object_, condition) representing a parsed
    behavior AC. Alias for :class:`ears_criteria.BehaviorCriterion`.
parse_behavior_criterion(ac) -> EARSBehavior | None
    Parse a ``behavior:`` AC string into a structured tuple.
    Returns ``None`` for non-behavior ACs; raises ``ValueError`` for
    malformed behavior ACs (prefix present but ``when`` clause missing).
parse_behavior_ac(ac) -> dict | None
    Parse a ``behavior:`` AC string into an evaluator-ready dict with keys:
    subject, verb, object, condition, evaluator_check, raw.
    Returns ``None`` for non-behavior ACs or malformed ACs.
"""

from __future__ import annotations

from ears_criteria import BehaviorCriterion, parse_behavior

#: Public name for the parsed behavior criterion tuple.
EARSBehavior = BehaviorCriterion


def parse_behavior_criterion(ac: str) -> EARSBehavior | None:
    """Parse a ``behavior:`` acceptance criterion into a structured tuple.

    Returns an :class:`EARSBehavior` if *ac* matches the behavior grammar,
    or ``None`` if *ac* does not start with the ``behavior:`` prefix.

    Raises ``ValueError`` for ACs that have the ``behavior:`` prefix but are
    otherwise malformed (e.g. missing the required ``when`` clause).

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        An :class:`EARSBehavior` when *ac* matches; ``None`` otherwise.

    Raises:
        ValueError: When *ac* starts with ``behavior:`` but lacks a ``when``
            clause or cannot be further parsed.

    Examples::

        >>> parse_behavior_criterion("behavior: parser returns BehaviorAC when AC matches grammar")
        EARSBehavior(subject='parser', verb='returns', object_='BehaviorAC',
                     condition='AC matches grammar')

        >>> parse_behavior_criterion("pytest: tests/test_foo.py")
        None
    """
    return parse_behavior(ac)


def parse_behavior_ac(ac: str) -> dict | None:
    """Parse a ``behavior:`` acceptance criterion into an evaluator-ready dict.

    Wraps :func:`parse_behavior_criterion` to produce a structured
    representation with all four parsed fields plus a generated verification
    prompt.

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        A dict with keys ``subject``, ``verb``, ``object``, ``condition``,
        ``evaluator_check``, and ``raw`` when *ac* matches the behavior
        grammar; ``None`` when *ac* does not start with the ``behavior:``
        prefix or is malformed (missing ``when`` clause).

    Examples::

        >>> parse_behavior_ac("behavior: parser returns BehaviorAC when AC matches grammar")
        {'subject': 'parser', 'verb': 'returns', 'object': 'BehaviorAC',
         'condition': 'AC matches grammar', 'evaluator_check': ..., 'raw': ...}

        >>> parse_behavior_ac("pytest: tests/test_foo.py")
        None
    """
    if not ac or not ac.strip():
        return None

    try:
        criterion = parse_behavior_criterion(ac)
    except ValueError:
        return None

    if criterion is None:
        return None

    evaluator_check = _build_evaluator_check(criterion)

    return {
        "subject": criterion.subject,
        "verb": criterion.verb,
        "object": criterion.object_,
        "condition": criterion.condition,
        "evaluator_check": evaluator_check,
        "raw": ac,
    }


def _build_evaluator_check(criterion: EARSBehavior) -> str:
    """Build a structured verification prompt from a parsed EARSBehavior."""
    lines = [
        "## Behavior AC Verification",
        "",
        "Verify the following behavior criterion using its parsed structure:",
        f"- **Subject**: {criterion.subject}",
        f"- **Verb**: {criterion.verb}",
        f"- **Object**: {criterion.object_}",
        f"- **Condition** (when): {criterion.condition}",
        "",
        "### Verification Steps",
        f"1. Locate code where `{criterion.subject}` is defined",
        f"2. Verify `{criterion.subject}` performs `{criterion.verb} {criterion.object_}`",
        f"3. Confirm this behavior triggers when `{criterion.condition}`",
        "4. Cite file:line references as evidence",
        "",
        "### Pass Criteria",
        "PASS when subject, verb+object, and condition are all correctly implemented.",
        "FAIL when any component is absent or not triggered by the condition.",
    ]
    return "\n".join(lines)


__all__ = ["EARSBehavior", "parse_behavior_ac", "parse_behavior_criterion"]
