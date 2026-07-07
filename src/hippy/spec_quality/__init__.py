"""hippy.spec_quality — spec-quality gates for the hippy pipeline.

Public API::

    from hippy.spec_quality import (
        BehaviorAC,
        accepts_synonym_conditional,
        parse_behavior_ac,
    )
"""

from hippy.spec_quality.behavior_ac_parser import (  # noqa: F401
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)

__all__ = ["BehaviorAC", "accepts_synonym_conditional", "parse_behavior_ac"]
