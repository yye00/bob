"""Canonical entry-point for the spec_quality behavior-AC parser.

Re-exports the implementation from ``bob.spec_quality.behavior_ac_parser``
so that callers can import from ``bob.spec_quality_ac_parser`` (the path
named in AC 737a5163).

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition" — overly-tight regex blocks 70%+
of well-formed behavior ACs.

Accepted clause forms
---------------------
1. Canonical: ``behavior: <subject> <verb> <object> when <condition>``
2. 'on' synonym: ``behavior: <subject> on <event> <verb> <object>``
3. 'on' suffix: ``behavior: <subject> <verb> <object> on <event>``
4. Compound predicate: any of the above with 'and' joining multiple verb phrases.
"""

from bob.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = ["BehaviorAC", "accepts_synonym_conditional", "parse_behavior_ac"]
