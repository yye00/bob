"""Spec quality package — top-level interface to bob3.spec_quality."""

from spec_quality.score import (  # noqa: F401
    calculate_spec_quality_score,
    compute_spec_quality_score,
    generate_remediation_report,
)
from spec_quality.behavior_ac_parser import (  # noqa: F401  # 2b3b9c5d integration
    BehaviorAC,
    accepts_synonym_conditional,
    parse_behavior_ac,
)
