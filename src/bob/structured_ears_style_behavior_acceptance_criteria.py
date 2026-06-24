"""Structured EARS-style behavior acceptance criteria — sixth AC grammar.

Adds a ``behavior: <subject> <verb> <object> when <condition>`` grammar to
bob's AC evaluator. At load time the AC string is parsed into a structured
(subject, verb, object, condition) tuple; the evaluator then uses those
discrete fields to produce a targeted verification prompt rather than relying
on freeform prose.

Public API
----------
structured_ears_style_behavior_acceptance_criteria(ac) -> dict | None
    Parse a ``behavior:`` AC string.  Returns a dict with keys
    ``raw``, ``subject``, ``verb``, ``object``, ``condition``, and
    ``evaluator_check``.  Returns ``None`` for non-behavior ACs.
"""

from __future__ import annotations

from bob.spec_quality.ears_parser import (
    BehaviorAC,
    parse_behavior_ac,
    evaluate_behavior_ac,
)


def structured_ears_style_behavior_acceptance_criteria(ac: str) -> dict | None:
    """Parse a ``behavior:`` AC and return a structured evaluation descriptor.

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    The returned dict contains the four parsed structural fields plus a
    pre-built ``evaluator_check`` string that references each field by name —
    so the independent evaluator grades the criterion using parsed structure,
    not freeform prose.

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        A dict with keys ``raw``, ``subject``, ``verb``, ``object``,
        ``condition``, and ``evaluator_check`` when *ac* matches the
        ``behavior:`` grammar; ``None`` otherwise (non-behavior ACs,
        malformed ACs, or empty string).
    """
    if not ac or not ac.strip():
        return None

    bac: BehaviorAC | None = parse_behavior_ac(ac.strip())
    if bac is None:
        return None

    return {
        "raw": ac.strip(),
        "subject": bac.subject,
        "verb": bac.verb,
        "object": bac.object,
        "condition": bac.condition,
        "evaluator_check": evaluate_behavior_ac(bac),
    }


__all__ = ["structured_ears_style_behavior_acceptance_criteria"]
