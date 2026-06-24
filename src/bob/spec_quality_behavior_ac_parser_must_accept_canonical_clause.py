"""Facade for the extended behavior-AC parser that accepts canonical clause forms.

Exposes ``spec_quality_behavior_ac_parser_must_accept_canonical_clause`` — a
dict-returning wrapper around :func:`bob.spec_quality.behavior_ac_parser.parse_behavior_ac`
that both accepts the canonical 'when' form and the 'on <event>' synonym form
(the F-R7-556 trigger case).

The underlying parser was tightened to accept:
  1. Canonical: ``behavior: <subject> <verb> <object> when <condition>``
  2. 'on' synonym: ``behavior: <subject> on <event> <verb> <object>``
  3. Compound predicates: ``verb phrase and verb phrase``
"""

from __future__ import annotations

from bob.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = [
    "BehaviorAC",
    "accepts_synonym_conditional",
    "parse_behavior_ac",
    "spec_quality_behavior_ac_parser_must_accept_canonical_clause",
]


def spec_quality_behavior_ac_parser_must_accept_canonical_clause(
    ac: str,
) -> dict:
    """Parse a behavior AC string and return a structured acceptance result.

    Accepts well-formed ACs using either the canonical 'when' form or the
    'on <event>' synonym form (F-R7-556).  Returns a dict with::

        {
            "accepted": bool,
            "raw": str,                    # original AC string (when accepted)
            "subject": str,               # parsed subject (when accepted)
            "verb": str,                  # parsed verb (when accepted)
            "condition": str,             # parsed condition (when accepted)
            "conditional_keyword": str,   # 'when' or 'on' (when accepted)
            "error": str,                 # error message (when rejected)
        }

    Args:
        ac: Raw behavior AC string.

    Returns:
        A dict with ``accepted`` = True on success or False on failure.
        On failure, ``error`` and ``reason`` keys explain why.
    """
    try:
        parsed: BehaviorAC = parse_behavior_ac(ac)
    except ValueError as exc:
        return {
            "accepted": False,
            "raw": ac,
            "error": str(exc),
            "reason": str(exc),
        }

    return {
        "accepted": True,
        "raw": parsed.raw,
        "subject": parsed.subject,
        "verb": parsed.verb,
        "object": parsed.object,
        "condition": parsed.condition,
        "conditional_keyword": parsed.conditional_keyword,
    }
