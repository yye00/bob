"""Bob AC handler patterns sub-package."""
# integration: bob.patterns — spec_quality_gate allowlist functions exposed here
from bob.spec_quality_gate import (  # noqa: F401  — integration: bob.patterns
    get_allowlist_config,
    is_feature_exempted,
    bypass_quality_threshold,
)

from bob.behavior_contract import (  # noqa: F401
    parse_behavior_contract,
    codegen_icontract_decorator,
    codegen_icontract_decorators,
)
from bob.deterministic_snapshots import enforce_maxfail_zero, snapshot_with_maxfail  # noqa: F401
from bob.schema_constrained_emission import (  # noqa: F401  — integration: bob.patterns
    emit_constrained_spec,
    validate_against_schema,
)
from bob.environment_capability_preflight import (  # noqa: F401  — integration: bob.patterns
    probe_dependencies,
    spawn_workaround_research,
    apply_workaround,
    run_preflight,
    check_environment_capabilities,
)
from bob.regression_detector import (  # noqa: F401  — integration: bob.patterns
    detect_regression_with_evidence,
    validate_causal_link,
)
from bob.artifact_verifier import (  # noqa: F401  — integration: bob.patterns
    validate_ac_artifact,
    verify_artifacts,
)
from bob.mutation_gate import (  # noqa: F401  — integration: bob.patterns
    run_mutation_tests,
    compute_mutation_score,
    check_mutation_score,
    MUTATION_SCORE_THRESHOLD,
)
from bob.pattern_9_shell_script_handler import demote_shell_script_ac  # noqa: F401  — integration: bob.patterns
from bob.boundary_error_coverage import (  # noqa: F401  — integration: bob.patterns
    detect_coverage_with_word_boundaries,
    filter_prose_acs,
)
from bob.startup_crash_exempt import (  # noqa: F401  — integration: bob.patterns
    is_transport_crash,
    should_exempt_from_retry,
    try_exempt,
    ExemptDecision,
    StartupCrashExemptOutcome,
)
def generate_k_candidates(*args, **kwargs):  # noqa: F401  — integration: bob.patterns
    """Lazy proxy to bob.codet_triangulation.generate_k_candidates (breaks circular import)."""
    from bob.codet_triangulation import generate_k_candidates as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def generate_kxk_matrix(*args, **kwargs):  # noqa: F401  — integration: bob.patterns
    """Lazy proxy to bob.codet_triangulation.generate_kxk_matrix (breaks circular import)."""
    from bob.codet_triangulation import generate_kxk_matrix as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def score_kxk_matrix(*args, **kwargs):  # noqa: F401  — integration: bob.patterns
    """Lazy proxy to bob.codet_triangulation.score_kxk_matrix (breaks circular import)."""
    from bob.codet_triangulation import score_kxk_matrix as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def mutual_agreement_scorer(*args, **kwargs):  # noqa: F401  — integration: bob.patterns
    """Lazy proxy to bob.codet_triangulation.mutual_agreement_scorer (breaks circular import)."""
    from bob.codet_triangulation import mutual_agreement_scorer as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)
