"""Extended behavior-AC parser for the spec_quality package.

Accepts canonical clause forms beyond the strict "subject verb object when
condition" pattern. The original parser only accepted "when" as the conditional
keyword. This module extends parsing to accept:

  - "on <event>" as a synonym for "when <condition>"
  - Compound predicates joined by "and" as a single verifiable clause

Delegates to bob3.spec_quality.behavior_ac_parser for the actual implementation.
"""

from __future__ import annotations

from bob3.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = [
    "BehaviorAC",
    "accepts_synonym_conditional",
    "parse_behavior_ac",
]
