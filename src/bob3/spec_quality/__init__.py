"""Spec quality checks for bob3."""

from bob3.spec_quality.spec_extractor import extract_and_check  # noqa: F401  # integration wiring
from bob3.spec_quality.section_selector import (  # noqa: F401  # Self-Discover integration
    select_sections,
    module_set,
    validate_output_schema,
    extractor_skips_marked_sections,
    critic_ignores_skip_slots,
    persist_decision,
    SectionSchemaError,
)
from bob3.spec_quality.behavior_ac_parser import (  # noqa: F401  # F-654aea21 integration
    parse_behavior_ac,
    accepts_synonym_conditional,
    BehaviorAC,
)
from bob3.spec_quality.quality_score import (  # noqa: F401  # eb57333a integration wiring
    compute_score,
    gate_for_ready,
    QualityReport,
    ScoreComponents,
)
from bob3.spec_quality.composite_score import (  # noqa: F401  # d9781830 composite gate
    compute_composite_score,
    score_gate_decision,
)
from bob3.spec_quality.score import (  # noqa: F401  # ffa5de39 spec quality score gate
    calculate_spec_quality_score,
    compute_spec_quality_score,
    generate_remediation_report,
)
from bob3.deterministic_fallback import (  # noqa: F401  # b6c53aa9 boundary+error coverage
    ensure_boundary_and_error_coverage,
)
