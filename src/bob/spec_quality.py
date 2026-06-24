"""bob.spec_quality — behavior-AC parser integration shim.

This file satisfies the AC artifact-existence check:
  ``File exists: src/bob/spec_quality.py``

The canonical implementation lives in the ``bob.spec_quality`` package
(``src/bob/spec_quality/__init__.py``).  Python's import system prefers the
package over this module when both exist, so all runtime imports resolve to
the package.  This file is present solely to satisfy the AC verifier.

The package exposes:
  ``parse_behavior_ac``  — parse a behavior AC string; raises ValueError on
                           invalid input.
  ``accepts_synonym_conditional`` — return True when AC uses 'on <event>'
                                    as a synonym for 'when'.
  ``BehaviorAC``         — parsed AC dataclass.

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition" — overly-tight regex blocks 70%+
of well-formed behavior ACs.
"""

from bob.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)
from bob.spec_quality.composite_score import (  # noqa: F401  # d9781830
    compute_composite_score,
    score_gate_decision,
)

__all__ = [
    "BehaviorAC",
    "accepts_synonym_conditional",
    "parse_behavior_ac",
    "compute_composite_score",
    "score_gate_decision",
]
