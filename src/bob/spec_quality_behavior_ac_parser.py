"""Standalone entry-point for the spec_quality behavior-AC parser.

Re-exports the canonical implementation from
``bob.spec_quality.behavior_ac_parser`` so that callers can import from
``bob.spec_quality_behavior_ac_parser`` (the path named in AC F-R7-556).

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition" — overly-tight regex blocks 70%+
of well-formed behavior ACs.
"""

from bob.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = ["BehaviorAC", "accepts_synonym_conditional", "parse_behavior_ac"]
