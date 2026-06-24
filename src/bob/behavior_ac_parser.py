"""Behavior-AC parser supporting extended canonical clause forms.

Re-exports the canonical implementation from
``bob.spec_quality.behavior_ac_parser`` so that callers can import from
``bob.behavior_ac_parser`` (the path named in AC F-2bd103a0).

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition" — overly-tight regex blocks 70%+
of well-formed behavior ACs.

The following clause forms are accepted:

  1. Canonical: ``behavior: <subject> <verb> <object> when <condition>``
  2. 'on' synonym: ``behavior: <subject> on <event> <verb> <object>``
  3. 'on' suffix:  ``behavior: <subject> <verb> <object> on <event>``
  4. Compound predicate: any of the above with 'and' joining multiple verb phrases.
"""

from bob.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)
from bob.acceptance_criteria.key_example import (  # noqa: F401
    KeyExample,
    extract_key_examples,
)

# Alias required by AC: "Function defined: bob.behavior_ac_parser.parse_behavior_clause"
parse_behavior_clause = parse_behavior_ac

__all__ = [
    "BehaviorAC",
    "KeyExample",
    "accepts_synonym_conditional",
    "extract_key_examples",
    "parse_behavior_ac",
    "parse_behavior_clause",
]
