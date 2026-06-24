"""Structured EARS-style behavior acceptance criterion grammar — sixth AC grammar.

Provides the ``behavior: <subject> <verb> <object> when <condition>`` grammar
for bob's AC evaluator. At load time the AC string is parsed into a structured
(subject, verb, object, condition) tuple; the evaluator uses those discrete
fields to produce a targeted verification prompt rather than relying on freeform
prose.

Public API
----------
BehaviorAC
    Dataclass (raw, subject, verb, object, condition) representing a parsed
    behavior AC. Re-exported from :mod:`bob.spec_quality.ears_parser`.
parse_behavior_ac(ac) -> BehaviorAC | None
    Parse a ``behavior:`` AC string. Returns a :class:`BehaviorAC` on success,
    or ``None`` for non-behavior ACs. Raises :class:`ValueError` for malformed
    behavior ACs (prefix present but ``when`` clause missing).
evaluate_behavior_ac(bac) -> str
    Build a structured grading prompt from a :class:`BehaviorAC` — for use by
    the independent evaluator.
"""

from __future__ import annotations

from bob.spec_quality.ears_parser import (
    BehaviorAC,
    EARSParseError,
    behavior_acs_from_criteria,
    build_behavior_ac_evaluator_section,
    evaluate_behavior_ac,
    parse_behavior_ac,
    raises_on_malformed,
)

__all__ = [
    "BehaviorAC",
    "EARSParseError",
    "behavior_acs_from_criteria",
    "build_behavior_ac_evaluator_section",
    "evaluate_behavior_ac",
    "parse_behavior_ac",
    "raises_on_malformed",
]
