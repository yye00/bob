"""EARS-style behavior acceptance criteria parser.

Provides the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>

At load time, parse_behavior parses the AC string into a structured
BehaviorCriterion tuple. The evaluator uses those discrete fields to
produce a targeted verification prompt rather than relying on freeform prose.

Public API
----------
BehaviorCriterion
    Named-tuple (subject, verb, object_, condition) representing a parsed
    behavior AC.
parse_behavior(ac) -> BehaviorCriterion | None
    Parse a behavior: AC string. Returns a BehaviorCriterion on
    success, or None for non-behavior ACs. Raises ValueError for
    malformed behavior ACs (prefix present but when clause missing).
"""

from __future__ import annotations

from ears_criteria import BehaviorCriterion, parse_behavior

__all__ = ["BehaviorCriterion", "parse_behavior"]
