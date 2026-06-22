"""
Bob3 Orchestrator - Sub-agent coordination and execution.

The orchestrator package manages the lifecycle of Claude Code sub-agents,
including spawning, orientation, task assignment, and result collection.

Key responsibilities:
- Spawning Claude Code sub-agents via the claude-code-sdk
- Providing orientation context to each sub-agent
- Managing MCP plugin configuration for sub-agents
- Tracking sub-agent progress and collecting results
"""

import pathlib

from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents  # noqa: F401 — feature 398757d8
from bob3.orchestrator_reaper import finalize_orphans_on_exit  # noqa: F401 — feature 22a11eb4
def sweep_orphans_on_exit(project_id: str):  # noqa: F401 — integration 457df9cf
    """Lazy proxy to bob3.final_reaper.sweep_orphans_on_exit — feature 457df9cf."""
    from bob3.final_reaper import sweep_orphans_on_exit as _fn  # noqa: PLC0415
    return _fn(project_id)
from bob3.orchestrator.stale_bytecode import should_relaunch_on_stale_bytecode  # noqa: F401 — feature fd401bd3
from bob3.orchestrator.stale_bytecode_guard import check_stale_bytecode  # noqa: F401 — feature 62309b12
from bob3.orchestrator.periodic_resume import resume_scan  # noqa: F401 — feature e072706e
from bob3.timeout import enforce_wall_clock_timeout as execute_feature_with_timeout  # noqa: F401 — feature 55304189
from bob3.timeout import enforce_wall_clock_timeout as enforce_feature_timeout  # noqa: F401 — feature 23dee915
from bob3.execution_timeout import enforce_feature_timeout as enforce_feature_execution_timeout  # noqa: F401 — integration f3a3f1c8
from bob72.spec_quality_gate import check_allowlist  # noqa: F401 — integration 9fd68b38
from bob3.spec_quality_gate import check_permanent_carry_allowlist  # noqa: F401 — integration 7c973615
from bob3.spec_quality_gate import check_quality_gate_exemption  # noqa: F401 — integration 44f5f8df
from bob3.spec_quality_gate import check_permanent_forward_carry_allowlist  # noqa: F401 — integration 0bd45c0b
from bob3.spec_quality_gate import check_permanent_forward_carry_exemption  # noqa: F401 — integration a7cbafdc
from bob3.spec_quality_gate import is_permanent_forward_carry  # noqa: F401 — integration fe834269
from bob3.spec_quality_gate import is_exempt_from_gate, load_allowlist  # noqa: F401 — integration 3f732534
from bob3.spec_quality_gate import check_quality_gate_with_allowlist  # noqa: F401 — integration 0eca77ce
from bob3.spec_quality_gate import check_quality_score_gate  # noqa: F401 — integration e36fa467
from bob3.orchestrator.run_loop import dispatch_concurrent_features  # noqa: F401 — feature 26a9ae10
from bob3.orchestrator_concurrent import ConcurrentDispatchSlot  # noqa: F401 — feature 1ea67181
from bob3.orchestrator_dispatch import dispatch_concurrent_features as dispatch_concurrent_features_v2  # noqa: F401 — feature f9de5db3
from bob3.run_loop import verify_project_metadata  # noqa: F401 — feature 4e25438f
from bob3.init_rerun_guard import verify_and_reinit_after_spawn  # noqa: F401 — feature 9e0d60de
from bob3.project_metadata_validator import (  # noqa: F401 — feature 1636b33f
    verify_project_name_matches_workspace,
    reinit_stale_projects,
)
from bob3.coordinator import merge_research_and_intent  # noqa: F401 — integration BF-2 2c44fc01
from bob3.self_discover_agent import select_spec_sections, run_focused_extraction  # noqa: F401 — integration 869cc539

import bob3.orchestrator.weekend_watchdog  # noqa: F401 — wires integration AC
from bob3.stuck_readiness import check_stuck_readiness, mark_pending_decomposition  # noqa: F401 — integration 40a21753
from bob3.convergence_checker import check_convergence, compare_by_name  # noqa: F401 — integration e6ce8805
from bob3.orchestrator.cost_telemetry_guard import apply_pessimistic_cost  # noqa: F401 — integration AC db93bf37
from bob3.orchestrator.cost_telemetry_guard import enforce_budget_on_zero_cost  # noqa: F401 — integration AC 7ac9cc81
from bob3.watchdog import escalate_stall_observation  # noqa: F401 — integration AC cf30a43e
from bob3.orchestrator.cost_telemetry_guard import enforce_budget_with_cost_telemetry_fallback  # noqa: F401 — integration AC 6845fe77
from bob3.orchestrator.cost_telemetry_guard import enforce_budget_with_telemetry_loss  # noqa: F401 — integration AC 52623df9
def enforce_minimum_cost_on_zero_report(*args, **kwargs):  # noqa: F401 — integration AC 5d25f312
    """Lazy proxy to bob3.cost_telemetry_guard.enforce_minimum_cost_on_zero_report.

    Lazy import breaks the circular dependency: bob3.cost_telemetry_guard
    imports bob3.orchestrator.cost_telemetry_guard (inner primitive), while
    bob3.orchestrator.__init__ imports bob3.cost_telemetry_guard (outer façade).
    """
    from bob3.cost_telemetry_guard import enforce_minimum_cost_on_zero_report as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)
from bob3.spec_synthesizer import synthesize_for_feature  # noqa: F401 — feature 82babf08
from bob3.synthesizer import parse_criteria_response, inject_boundary_error_criteria  # noqa: F401 — integration fa334558
from bob3.peas_synthesizer import parse_peas_markdown, synthesize_features as synthesize_peas_features  # noqa: F401 — integration fb2f2776
from bob3.extract_from_peas import extract_features_from_peas, run_pipeline as run_peas_pipeline  # noqa: F401 — integration d7473f36
from bob3.ears_criteria import BehaviorCriterion, parse_behavior_criterion  # noqa: F401 — feature 9519276f
from bob3.ears_behavior_parser import parse_behavior_ac  # noqa: F401 — feature 979ba466
from bob3.contract_grammar import validate_lambda_bindings  # noqa: F401 — integration c6d4f48e
from bob3.carry_forward_auditor import match_by_canonical_id, evaluate_canonical_carry  # noqa: F401 — integration cf02cdc2
from bob3.forward_carry_auditor import audit_forward_carry_by_canonical_id  # noqa: F401 — integration 1e04ed4d
from bob3.spec_writer import atomic_write, quarantine_corrupt_yaml  # noqa: F401 — integration d6aa0a0e
from bob3.mutation_testing_gate import run_mutation_tests, validate_mutation_score, check_mutation_score  # noqa: F401 — integration 16f38058
from bob3.mutation_verifier import run_mutation_testing  # noqa: F401 — integration d27599e6
from bob3.spec_findings_registry import write_findings, detect_regression as detect_spec_regression  # noqa: F401 — integration 833ba464
from bob3.verifier import scope_pytest_to_feature, SiblingTestCollectionError  # noqa: F401 — integration a1928d83
from bob3.verifier_scoped_tests import scope_pytest_to_feature as scope_pytest_to_feature_scoped  # noqa: F401 — integration 06cb1af5
from bob3.boundary_error_coverage import (  # noqa: F401 — integration 7816ec72
    detect_coverage_with_boundaries,
    detect_coverage_with_word_boundaries,
    ensure_boundary_and_error_coverage,
    filter_prose_acs,
    get_prose_acs,
    is_prose_ac,
)
from bob3.boundary_error_coverage_detector import (  # noqa: F401 — integration 15768c50
    detect_coverage_with_word_boundaries as _detector_detect_coverage_with_word_boundaries,
    filter_prose_acs as _detector_filter_prose_acs,
)
from bob3.orchestrator.spawn_retry import classify_exit, spawn_with_retry  # noqa: F401 — integration 56d40cab
from bob3.triton_kernel_synthesis import synthesize_and_autotune, verify_numerical_correctness  # noqa: F401 — integration 6cc31a74
from bob3.gpu_kernel_synthesizer import synthesize_triton_kernel, autotune_kernel_config  # noqa: F401 — integration 81c05422
from bob3.triton_kernel_synthesizer import (  # noqa: F401 — integration 3c37bd53
    synthesize_triton_kernel as _tks_synthesize,
    autotune_kernel_config as _tks_autotune,
    verify_numerical_correctness as _tks_verify,
)
def _import_gpu_kernel_synthesis():  # noqa: F401 — integration b98a16b8 (lazy to avoid circular import)
    from bob3.gpu_kernel_synthesis import synthesize_triton_kernel, autotune_kernel_config  # noqa: PLC0415
    return synthesize_triton_kernel, autotune_kernel_config
from bob3.db import create_agent_run  # noqa: F401 — integration d5959824
from bob3.reaper_backoff import calculate_backoff_delay, should_refuse_redispatch as reaper_backoff_should_refuse  # noqa: F401 — integration 97e58db1
from bob3.smell_linter import lint_spec_for_smells  # noqa: F401 — integration c120febe
from bob3.linter_22 import detect_all_smells, SmellSeverity  # noqa: F401 — integration 91f40110
from bob3.schema_constraint import validate_spec_against_schema, apply_constrained_decoding  # noqa: F401 — integration 7d600b45
from bob3.spawn_reinit_guard import verify_project_metadata as verify_spawn_reinit_project_metadata  # noqa: F401 — integration 6b1704f0
from bob3.bootstrap import check_bootstrap_override  # noqa: F401 — integration eec43f5d
from bob3.bootstrap_readiness_override import check_bootstrap_bypass  # noqa: F401 — integration a69951c5
from bob3.self_discover_meta_agent import (  # noqa: F401 — integration b3620c07
    select_spec_sections,
    run_focused_extractor,
    focused_extractor,
    select_relevant_spec_sections,
    extract_with_selected_sections,
)
from bob3.permanent_forward_carry_auditor import audit_canonical_feature_ids  # noqa: F401 — integration 8b63922a
from bob3.ac_smell_rewriter import apply_suggested_rewrite, verify_semantic_equivalence as verify_ac_semantic_equivalence  # noqa: F401 — integration 4ff8bda2
from bob3.integration_target_checker import verify_integration_targets as check_integration_target_reachability  # noqa: F401 — integration 48a60b08
from bob3.spec_extractor import reject_behavior_acs_for_verifier_extensions  # noqa: F401 — integration 92221849
from bob3.spec_quality_score import compute_spec_quality_score, generate_remediation_report  # noqa: F401 — integration 38cdc579
from bob3.spec_quality_score import compute_composite_quality_score, evaluate_quality_gate  # noqa: F401 — integration 373d501a


def initialize_project_database(project_path: "pathlib.Path | str | None" = None, *, db_path: "pathlib.Path | None" = None) -> "pathlib.Path":
    """Resolve and initialise the project's SQLite database, returning its absolute path.

    This function ensures that every orchestration entry-point resolves the
    same database file regardless of cwd or sub-agent working directory:

    Resolution order:
      1. Explicit ``db_path`` argument (highest priority)
      2. ``BOB3_DATABASE_PATH`` environment variable
      3. ``<project_path>/bob3.db`` when ``project_path`` is supplied
      4. ``cwd/bob3.db`` (same fallback as :func:`bob3.db.get_database_path`)

    The resolved path is set on ``BOB3_DATABASE_PATH`` so every subsequent
    :func:`bob3.db.connect` call (and all spawned sub-agents that inherit the
    environment) targets the identical file.

    Args:
        project_path: Root directory of the bob3 project.  When supplied and
            no other override is in effect, the database is expected at
            ``<project_path>/bob3.db``.
        db_path: Explicit, fully-resolved path to the database file. Overrides
            all other resolution mechanisms.

    Returns:
        The absolute :class:`pathlib.Path` of the resolved database file.
    """
    import logging as _logging
    import os as _os
    from bob3 import db as _db

    _log = _logging.getLogger(__name__)

    resolved: pathlib.Path
    if db_path is not None:
        resolved = pathlib.Path(db_path).resolve()
    elif _os.environ.get("BOB3_DATABASE_PATH"):
        resolved = pathlib.Path(_os.environ["BOB3_DATABASE_PATH"]).resolve()
    elif project_path is not None:
        resolved = (pathlib.Path(project_path) / "bob3.db").resolve()
    else:
        resolved = _db.get_database_path().resolve()

    # Export so sub-agents and all subsequent connect() calls use the same DB.
    _os.environ["BOB3_DATABASE_PATH"] = str(resolved)
    _log.info("initialize_project_database: resolved DB path = %s", resolved)
    return resolved
from bob3.stale_bytecode_guard import check_stale_orchestrator_files  # noqa: F401 — integration 77618703
from bob3.stale_bytecode_guard import check_orchestrator_staleness  # noqa: F401 — integration 42e6183e
from bob3.stale_bytecode_guard import should_relaunch_on_stale_bytecode  # noqa: F401 — integration 7f6da6c1
from bob3.stale_bytecode import check_stale_bytecode as check_stale_bytecode_guard_at_relaunch  # noqa: F401 — integration 0769add9
from bob3.synth_retry import synthesize_with_retry, retry_with_backoff  # noqa: F401 — integration 0a8f9722
from bob3.blame_cascade import charge_failing_features  # noqa: F401 — integration 2f2050c0
from bob3.blame_cascade import charge_failing_test_to_feature  # noqa: F401 — integration 001d85e1
from bob3.blame_cascade import charge_to_owning_feature  # noqa: F401 — integration 65236321
from bob3.blame_cascade import charge_breaking_feature  # noqa: F401 — integration 7da96f66
from bob3.blame_the_cause import charge_failing_feature  # noqa: F401 — integration c5c2c05e
from bob3.blame_the_cause import charge_failing_features as charge_failing_features_blame_the_cause  # noqa: F401 — integration 0c5f8168
from bob3.blame_the_cause import charge_regression_cascade  # noqa: F401 — integration 43bfef8a
from bob3.sticky_completed_gate import is_sticky_completed, reset_sticky_completed_stamp  # noqa: F401 — integration 3752965b
from bob3.subagent_verification import forbid_pytest_stdout_redirection  # noqa: F401 — integration 772bd0b9
from bob3.environment_capability import probe_dependencies as probe_env_dependencies, discover_workaround  # noqa: F401 — integration 86baf307
from bob3.environment_capability_preflight import probe_dependencies, apply_workaround as apply_dep_workaround  # noqa: F401 — integration 158bd7a7
from bob3.research_strategies import (  # noqa: F401 — integration 7ce7f72a
    emit_canonical_acs,
    validate_against_spec_quality_gate,
)
from bob3.readiness_derivation import derive_readiness_score, seed_zero_readiness_features  # noqa: F401 — integration 3205cc9d
from bob3.run_loop import readiness_seed_sweep  # noqa: F401 — integration 8a13503e
def _codet_accessor(name):
    # True lazy proxy: only import bob3.codet when the attribute is accessed,
    # not at orchestrator.__init__ load time. This breaks the circular chain:
    # bob3.codet → bob3.codet_matrix → bob3.orchestrator.codet_triangulation →
    # bob3.orchestrator.__init__ → (would re-import bob3.codet, circular).
    import bob3.codet as _m  # noqa: PLC0415
    return getattr(_m, name)


def score_kxk_matrix(*args, **kwargs):
    """Proxy to bob3.codet.score_kxk_matrix — integration b2ec11a1."""
    return _codet_accessor("score_kxk_matrix")(*args, **kwargs)


def spawn_candidate_tests(*args, **kwargs):
    """Proxy to bob3.codet.spawn_candidate_tests — integration b2ec11a1."""
    return _codet_accessor("spawn_candidate_tests")(*args, **kwargs)


def spawn_candidate_impls(*args, **kwargs):
    """Proxy to bob3.codet.spawn_candidate_impls — integration b2ec11a1."""
    return _codet_accessor("spawn_candidate_impls")(*args, **kwargs)


def _codet_mutual_agreement_accessor(name):
    import bob3.codet_mutual_agreement as _m  # noqa: PLC0415
    return getattr(_m, name)


def spawn_k_candidates(*args, **kwargs):
    """Proxy to bob3.codet_mutual_agreement.spawn_k_candidates — integration 468d85bb."""
    return _codet_mutual_agreement_accessor("spawn_k_candidates")(*args, **kwargs)


def build_kxk_matrix(*args, **kwargs):
    """Proxy to bob3.codet_mutual_agreement.build_kxk_matrix — integration 0dbe5b92."""
    return _codet_mutual_agreement_accessor("build_kxk_matrix")(*args, **kwargs)


def score_mutual_agreement(*args, **kwargs):
    """Proxy to bob3.codet_mutual_agreement.score_mutual_agreement — integration 0dbe5b92."""
    return _codet_mutual_agreement_accessor("score_mutual_agreement")(*args, **kwargs)


from bob3.schema_constrained_emission import emit_with_schema, validate_and_reject_invalid  # noqa: F401 — integration ef6726c9
from bob3.brownfield.survey import (  # noqa: F401 — BF-1 integration AC dab037e6
    index_repository,
    refresh_survey,
    compute_pagerank,
)
from bob3.brownfield.patch_planner import (  # noqa: F401 — BF-7 integration AC be3df4dd
    plan_diff,
    plan_diffs,
    emit_diff_plan,
    apply_diff_plan,
    rollback_changes,
    check_scope_guard,
)
from bob3.meta_agent.self_discover import (  # noqa: F401 — integration 14d1c097
    select_spec_sections,
    run_focused_extractor,
)
from bob3.self_discover import (  # noqa: F401 — integration d322b8cc
    select_spec_sections as self_discover_select_spec_sections,
    focused_extractor_pass,
)
from bob3.gate_resynth import resynthesize_gate_blocked_feature  # noqa: F401 — feature 090dd381
from bob3.gate_synthesizer import re_synthesize_gate_blocked_feature  # noqa: F401 — feature a61c0e92
from bob3.score_gate_loop import (  # noqa: F401 — feature 7c98d6c7
    resynthesize_gate_blocked_features,
    is_already_resynthesized,
    robust_import_scorer,
)
from bob3.score_gate_loop import resynthesize_gate_blocked_features as promote_gate_blocked_features  # noqa: F401 — feature d987030c
from bob3.spec_synthesizer import score_gate_loop  # noqa: F401 — feature 797ae88c
from bob3.gate_blocked_resynthesis import (  # noqa: F401 — feature d5671a1a
    resynthesize_gate_blocked_feature as resynthesize_gate_blocked_feature_mid_run,
    is_resynthesis_attempted,
)
from bob3.gate_blocked_synthesizer import (  # noqa: F401 — feature adb882e4 / a29fdc98
    re_synthesize_blocked_feature,
    resynthesize_gate_blocked_feature,
    is_resynthesis_attempted as is_gate_blocked_resynthesis_attempted,
    mark_resynthesized,
)

def enforce_budget_on_zero_cost_with_work_events(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Proxy to bob3.cost_telemetry.enforce_budget_on_zero_cost_with_work_events.

    Defined here (rather than imported at module level) to avoid a circular
    import: bob3.cost_telemetry imports from bob3.orchestrator.cost_telemetry_guard,
    which would re-enter bob3.orchestrator.__init__ before cost_telemetry is loaded.
    """
    from bob3.cost_telemetry import enforce_budget_on_zero_cost_with_work_events as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def enforce_budget_with_telemetry_safety(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Alias for enforce_budget_on_zero_cost_with_work_events (AC 554f8848).

    Zero-reported-cost MUST NOT disable budget enforcement. This alias satisfies
    the AC requiring bob3.orchestrator.enforce_budget_with_telemetry_safety.
    """
    return enforce_budget_on_zero_cost_with_work_events(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def enforce_cost_floor_on_zero_report(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Proxy to bob3.cost_telemetry_guardian.enforce_cost_floor_on_zero_report.

    Defined here as a lazy proxy to avoid a circular import: the guardian module
    imports from bob3.orchestrator.cost_telemetry_guard (inside this package),
    which would re-enter bob3.orchestrator.__init__ before the guardian is loaded.

    Integration AC 754a4bf4: zero-reported-cost MUST NOT disable budget enforcement.
    """
    from bob3.cost_telemetry_guardian import enforce_cost_floor_on_zero_report as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def validate_reported_cost(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Proxy to bob3.cost_enforcement.validate_reported_cost.

    Defined here as a lazy proxy to avoid the circular import that arises when
    bob3.cost_enforcement imports bob3.orchestrator.cost_telemetry_guard, which
    would re-enter bob3.orchestrator.__init__ before cost_enforcement is loaded.
    """
    from bob3.cost_enforcement import validate_reported_cost as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def log_cost_telemetry_lost(
    feature_id,
    work_events,
    exit_code,
    attempt_number,
    applied_pessimistic_cost,
):
    """Proxy to bob3.cost_enforcement.log_cost_telemetry_lost.

    Defined here as a lazy proxy to avoid the same circular import as above.
    """
    from bob3.cost_enforcement import log_cost_telemetry_lost as _fn  # noqa: PLC0415
    return _fn(
        feature_id=feature_id,
        work_events=work_events,
        exit_code=exit_code,
        attempt_number=attempt_number,
        applied_pessimistic_cost=applied_pessimistic_cost,
    )


def validate_cost_and_events(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Proxy to bob3.cost_enforcement.validate_cost_and_events.

    Lazy proxy to avoid circular imports at module load time.
    """
    from bob3.cost_enforcement import validate_cost_and_events as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def should_treat_cost_as_unknown(
    reported_cost,
    work_events,
):
    """Proxy to bob3.cost_enforcement.should_treat_cost_as_unknown.

    Lazy proxy to avoid circular imports at module load time.
    """
    from bob3.cost_enforcement import should_treat_cost_as_unknown as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
    )


def enforce_zero_cost_policy(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Proxy to bob3.cost_enforcement.enforce_zero_cost_policy.

    Lazy proxy to avoid circular imports at module load time.
    Raises ValueError when per_feature_ceiling <= 0.
    """
    from bob3.cost_enforcement import enforce_zero_cost_policy as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def should_enforce_budget(
    reported_cost,
    work_events,
):
    """Proxy to bob3.cost_enforcement.should_enforce_budget.

    Lazy proxy to avoid circular imports at module load time.
    Returns True when budget enforcement must proceed (cost > 0 or work was done).
    Returns False only for genuine spawn-crash free-retry (cost == 0, work_events == 0).
    """
    from bob3.cost_enforcement import should_enforce_budget as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
    )


def enforce_zero_cost_threshold(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Proxy to bob3.cost_enforcement.enforce_zero_cost_policy — AC 64aefa92.

    Enforces the invariant: zero-reported-cost MUST NOT disable budget enforcement.
    When reported_cost==0 AND work_events > threshold, treats cost as
    UNKNOWN-but-nonzero and applies per_feature_ceiling as a pessimistic charge.
    Raises ValueError for invalid per_feature_ceiling (<= 0).
    """
    from bob3.cost_enforcement import enforce_zero_cost_policy as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


from bob3.verifier.baseline_gate import (  # noqa: F401 — integration AC 5c2b61ff
    abort_on_collection_failure,
    BaselineUnstableError,
)
from bob3.orchestrator.detect_regression import detect_regression  # noqa: F401 — integration AC aaa5a7f7
from bob3.parent_gen_db import read_parent_features, stamp_child_row  # noqa: F401 — integration AC F-R7-422
from bob3.parent_gen_inheritance import read_parent_generation  # noqa: F401 — integration AC 6d773884
from bob3.parent_gen_inheritance import stamp_child_row as stamp_child_row_inheritance  # noqa: F401 — integration AC 6d773884
from bob3.parent_gen import stamp_parent_metadata  # noqa: F401 — integration AC 8766ef8e F-R7-400
from bob3.parent_gen_db_inheritance import stamp_parent_metadata as stamp_parent_metadata_v2  # noqa: F401 — integration AC e4e92256 F-R7-400
from bob3.seed_inheritance import stamp_parent_generation  # noqa: F401 — integration AC 6a13e88d F-R7-400
from bob3.brownfield.elicit import (  # noqa: F401 — BF-3 integration AC 3e56d6b2
    extract_intent,
    classify_intent,
    score_ambiguity,
    apply_clarification_gate,
)
from bob3.brownfield.resurrection import (  # noqa: F401 — BF-5 integration AC bdb12e42
    detect_resurrection_signals,
    detect_stale_pr,
    detect_stale_branch,
    detect_export_without_impl,
    detect_exported_stubs,
    detect_todo_clusters,
    write_resurrection_report,
)
from bob3.orchestrator.verifier_self_reference import (  # noqa: F401 — integration AC 3c4912e1
    detect_verifier_self_reference,
)
from bob3.pending_successor_verify import (  # noqa: F401 — integration AC 6032ec54
    detect_verification_features,
    scan_ac_body_for_tokens,
)
from bob3.pending_successor_verifier import (  # noqa: F401 — integration AC 0b186833 (F-R7-596)
    detect_pending_successor_verify as _detect_psv_broadened,
)
from bob3.successor_verification import set_pending_successor_verify  # noqa: F401 — integration AC afe52d5b
from bob3.regression_detection import (  # noqa: F401 — integration AC dc8d200e
    detect_regression_with_evidence,
    has_causal_evidence,
    has_causal_link,
)
from bob3.regression_ownership_detector import (  # noqa: F401 — integration AC 5d250d36
    detect_regression_with_ownership,
    has_ownership_evidence,
)
from bob3.regression import (  # noqa: F401 — integration AC 270d01f1
    check_regression_ownership,
    find_touching_commits,
)
from bob3.orchestrator.prompt_source_reloader import maybe_reload_all  # noqa: F401 — integration AC e1bb8261
from bob3.brownfield.search_subagent import (  # noqa: F401 — integration AC 5c5826d3
    spawn_search_subagent,
    SearchResult,
    SearchCandidate,
    should_use_search_subagent,
    search_results_to_edit_sites,
)
from bob3.brownfield.multi_candidate_patch import (  # noqa: F401 — integration AC 5c5826d3
    is_hard_feature,
    judge_candidates,
    judge_patch_quality,
    maybe_run_multi_candidate,
    run_multi_candidate,
    spawn_worker_candidates,
)


from bob3.orchestrator.plan_gate import (  # noqa: F401 — integration AC bcb6a22e
    emit_plan_ready_event,
    write_plan_artifact,
    is_approved,
    approve_plan,
    refuse_implementer_when_unapproved,
    compute_plan_vs_spec_drift,
    load_plan,
)
from bob3.bidirectional_requirements_traceability_matrix_rtm_artifact import (  # noqa: F401 — integration AC 731c750d
    bidirectional_requirements_traceability_matrix_rtm_artifact,
    check_halt_gate as rtm_check_halt_gate,
)
from bob3.uncertainty_loop import (  # noqa: F401 — integration AC a3ec8a14
    generate_candidate_stubs,
    compute_disagreement_slots,
    mark_ambiguous_slots,
    batch_clarification_questions,
)
from bob3.spec_uncertainty_clarifier import (  # noqa: F401 — integration AC 5a7be040
    generate_candidate_stubs as spec_generate_candidate_stubs,
    detect_disagreement_slots,
    batch_clarification_questions as spec_batch_clarification_questions,
)
def research_augmented_retry(*args, **kwargs):
    """Lazy proxy to bob3.retry_strategy.research_augmented_retry — integration AC 85ebd727."""
    from bob3.retry_strategy import research_augmented_retry as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def classify_retry_failure(failure_info):
    """Lazy proxy to bob3.retry_strategy.classify_failure — integration AC 85ebd727."""
    from bob3.retry_strategy import classify_failure as _fn  # noqa: PLC0415
    return _fn(failure_info)


def spawn_research_agent(failure_class_str: str) -> bool:
    """Lazy proxy to bob3.retry_strategy.spawn_research_agent — integration AC 85ebd727."""
    from bob3.retry_strategy import spawn_research_agent as _fn  # noqa: PLC0415
    return _fn(failure_class_str)

ORCHESTRATOR_DIR = pathlib.Path(__file__).parent


def scan_pending_successor_verify(
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Scan a feature's ACs and trigger pending_successor_verify deferral when warranted.

    At feature-claim time (before the test-writer sub-agent runs), scans
    ``acceptance_criteria`` for any AC whose body contains a verifier path-token
    OR whose prefix is ``behavior:`` and references verifier-internal symbols.
    Also applies the title-fallback for features whose name contains 'verifier'.

    This is the broadened pre-dispatch scanner introduced in F-R7-596 and
    auto-defer spec (00092d98). It delegates to
    ``bob3.pending_successor_verify.detect_verification_features`` which
    implements the full detection logic including path-token scanning and
    title-fallback.

    Args:
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.
                              Any other type raises ValueError.

    Returns:
        True when the feature should be deferred to the successor generation.
        False otherwise (including on any parse error).

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    if acceptance_criteria is not None and not isinstance(acceptance_criteria, (list, str)):
        raise ValueError(
            f"scan_pending_successor_verify: acceptance_criteria must be a list, "
            f"str, or None; got {type(acceptance_criteria).__name__!r}"
        )
    from bob3.pending_successor_verify import detect_verification_features  # noqa: PLC0415
    return detect_verification_features(feature_name, acceptance_criteria)


def detect_pending_successor_verify(
    acceptance_criteria,
) -> bool:
    """Detect whether a feature's ACs trigger the pending_successor_verify deferral.

    At feature-claim time, scans ``acceptance_criteria`` for any AC whose
    prefix is ``behavior:`` and whose body references verifier-internal symbols
    (``enhanced_verification``, ``verifier``, ``_check_criterion``, ``_demote_``).
    When matched, the feature should be deferred to the successor generation
    via ``status='pending_successor_verify'`` instead of being dispatched.

    This is the detection half of the deferral mechanism — it returns True
    when the self-reference treadmill would be triggered.  Use
    ``defer_verifier_self_extension`` to also apply the DB status update.

    Args:
        acceptance_criteria: A list of AC strings, a JSON-encoded list of AC
                             strings, or None.  Any other type raises ValueError.

    Returns:
        True when at least one behavior: AC references a verifier-internal
        keyword.  False otherwise (including on any parse error).

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    if acceptance_criteria is not None and not isinstance(acceptance_criteria, (list, str)):
        raise ValueError(
            f"detect_pending_successor_verify: acceptance_criteria must be a list, "
            f"str, or None; got {type(acceptance_criteria).__name__!r}"
        )
    from bob3.orchestrator.verifier_self_reference import detect_verifier_self_reference
    return detect_verifier_self_reference(acceptance_criteria)


def reload_prompt_sources() -> list[str]:
    """Hot-reload all watched prompt-source modules if their on-disk source has changed.

    Call once before each subagent dispatch.  Checks the mtime of every
    module in the watch-list (currently ``bob3.superpowers`` and
    ``bob3.models``); if any has changed since the last check, calls
    importlib.reload() so the updated module-level constants
    (VERIFICATION_PROMPT_SECTION, SKILLS_PROMPT_SECTION, etc.) are
    visible to the next dispatch without requiring an orchestrator restart.

    Cheap: one stat(2) + dict lookup per module per call.
    Bounded: reloads only when the file actually changed.

    Returns:
        List of module names that were reloaded (empty when all are
        up-to-date or when no files have changed).
    """
    import bob3.orchestrator.prompt_source_reloader as _reloader
    return _reloader.maybe_reload_all()


def reload_prompt_source_if_changed(module_name: str = "bob3.superpowers") -> bool:
    """Hot-reload a single prompt-source module if its on-disk source has changed.

    Checks the mtime of *module_name*'s source file and calls
    importlib.reload() only when the file has been modified since the last
    check.  Designed for per-dispatch use: cheap (one stat + dict lookup)
    and bounded (reloads only on actual changes).

    Args:
        module_name: Dotted module name to check and optionally reload.
                     Defaults to ``bob3.superpowers`` — the primary source
                     of VERIFICATION_PROMPT_SECTION and SKILLS_PROMPT_SECTION.

    Returns:
        True if the module was reloaded, False if it was already up-to-date
        or the module file could not be found.
    """
    import bob3.orchestrator.prompt_source_reloader as _reloader
    return _reloader.reload_if_stale(module_name)


def reload_prompt_sources_if_changed() -> list[str]:
    """Hot-reload all watched prompt-source modules if their on-disk source has changed.

    Call once before each subagent dispatch.  Checks the mtime of every
    module in the watch-list (currently ``bob3.superpowers`` and
    ``bob3.models``); if any has changed since the last check, calls
    importlib.reload() so the updated module-level constants
    (VERIFICATION_PROMPT_SECTION, SKILLS_PROMPT_SECTION, etc.) are
    visible to the next dispatch without requiring an orchestrator restart.

    Cheap: one stat(2) + dict lookup per module per call.
    Bounded: reloads only when the file actually changed.

    Returns:
        List of module names that were reloaded (empty when all are
        up-to-date or when no files have changed).
    """
    import bob3.orchestrator.prompt_source_reloader as _reloader
    return _reloader.maybe_reload_all()


def defer_verifier_self_extension(
    feature_id: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation if its behavior: ACs target verifier internals.

    At feature-claim time, scans the acceptance_criteria for any AC whose
    prefix is ``behavior:`` and whose body references verifier-internal symbols
    (``enhanced_verification``, ``verifier``, ``_check_criterion``, ``_demote_``).
    When matched, updates the feature row to ``status='pending_successor_verify'``
    and returns True so the orchestrator can skip sub-agent dispatch.

    This breaks the self-reference treadmill: the running verifier cannot
    validate behavior it does not yet implement, so such features always fail
    in their own generation.  Deferring them hands off to the successor
    generation whose verifier already has the new code baked in.

    Args:
        feature_id:          UUID of the feature to potentially defer.
        acceptance_criteria: A list of AC strings or a JSON-encoded list.

    Returns:
        True when the feature was deferred (status set to
        ``'pending_successor_verify'``).  False when no verifier-self-reference
        was detected or when the DB update fails.
    """
    import logging
    from bob3 import db
    from bob3.orchestrator.verifier_self_reference import detect_verifier_self_reference

    _logger = logging.getLogger(__name__)

    if not detect_verifier_self_reference(acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status="pending_successor_verify")
        _logger.info(
            "defer_verifier_self_extension: feature %s deferred to successor gen "
            "(behavior: AC references verifier internals)",
            feature_id,
        )
        return True
    except Exception:
        _logger.error(
            "defer_verifier_self_extension: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def check_pending_successor_verify(
    acceptance_criteria,
) -> bool:
    """Check whether a feature's ACs trigger the pending_successor_verify deferral.

    At feature-claim time, scans ``acceptance_criteria`` for any AC whose
    prefix is ``behavior:`` and whose body references verifier-internal symbols
    (``enhanced_verification``, ``verifier``, ``_check_criterion``, ``_demote_``).

    When any such AC is detected, the feature should be deferred to the successor
    generation via ``status='pending_successor_verify'`` instead of being dispatched
    to a sub-agent.  Use ``defer_verifier_self_reference`` to also apply the DB
    status update.

    Args:
        acceptance_criteria: A list of AC strings, a JSON-encoded list of AC
                             strings, or None.

    Returns:
        True when at least one behavior: AC references a verifier-internal
        keyword.  False otherwise (including on any parse error).
    """
    from bob3.orchestrator.verifier_self_reference import detect_verifier_self_reference
    return detect_verifier_self_reference(acceptance_criteria)


def defer_verifier_self_reference(
    feature_id: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation when behavior: ACs target verifier internals.

    At feature-claim time, scans the acceptance_criteria for any AC whose
    prefix is ``behavior:`` and whose body references verifier-internal symbols
    (``enhanced_verification``, ``verifier``, ``_check_criterion``, ``_demote_``).
    When matched, updates the feature row to ``status='pending_successor_verify'``
    and returns True so the orchestrator can skip sub-agent dispatch.

    This breaks the self-reference treadmill: the running verifier cannot
    validate behavior it does not yet implement, so such features always fail
    in their own generation.  Deferring them hands off to the successor
    generation whose verifier already has the new code baked in.

    Args:
        feature_id:          UUID of the feature to potentially defer.
        acceptance_criteria: A list of AC strings or a JSON-encoded list.

    Returns:
        True when the feature was deferred (status set to
        ``'pending_successor_verify'``).  False when no verifier-self-reference
        was detected or when the DB update fails.
    """
    import logging
    from bob3 import db
    from bob3.orchestrator.verifier_self_reference import detect_verifier_self_reference

    _logger = logging.getLogger(__name__)

    if not detect_verifier_self_reference(acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status="pending_successor_verify")
        _logger.info(
            "defer_verifier_self_reference: feature %s deferred to successor gen "
            "(behavior: AC references verifier internals)",
            feature_id,
        )
        return True
    except Exception:
        _logger.error(
            "defer_verifier_self_reference: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def defer_to_pending_successor_verify(
    feature_id: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation when its ACs target verifier internals.

    At feature-claim time (before the test-writer sub-agent runs), scans
    ``acceptance_criteria`` for any AC whose body contains a verifier path-token
    OR whose prefix is ``behavior:`` and references verifier-internal symbols.
    When matched, updates the feature row to ``status='pending_successor_verify'``
    and returns True so the orchestrator can skip sub-agent dispatch.

    This is the primary entry point for the auto-defer mechanism introduced in
    this feature spec (d876f83f). It combines detection (via
    ``detect_pending_successor_verify``) with the DB status transition, breaking
    the self-reference treadmill where verifier-extension features always fail in
    their own generation.

    Args:
        feature_id:          UUID of the feature to potentially defer.
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was deferred (status set to
        ``'pending_successor_verify'``).  False when no verifier-self-reference
        was detected or when the DB update fails.

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    import logging
    from bob3 import db

    _logger = logging.getLogger(__name__)

    if not detect_pending_successor_verify(acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status="pending_successor_verify")
        _logger.info(
            "defer_to_pending_successor_verify: feature %s deferred to successor gen "
            "(AC references verifier internals)",
            feature_id,
        )
        return True
    except Exception:
        _logger.error(
            "defer_to_pending_successor_verify: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def resume_interrupted_work(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Module-level entry point for the periodic resume scan (feature 2d9615ff).
    Delegates to ``bob3.orchestrator.periodic_resume_scan.periodic_resume_scan``
    so that interrupted rows are re-queued without requiring an orchestrator
    restart.

    Called on every orchestrator tick (or a dedicated 60 s timer) so that a
    feature cancelled mid-run (max_turns hit, async timeout, etc.) is
    re-queued without requiring a relaunch.

    Combined with F-R7-501 (stuck-executing reaper) this eliminates the two
    paths by which the orchestrator silently stalls on rows it should
    re-dispatch.

    Args:
        project_id: UUID of the project to scan.  Must be a non-empty string.

    Returns:
        List of feature IDs promoted from 'interrupted' to 'ready'.

    Raises:
        ValueError: If *project_id* is not a non-empty string.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(
            f"project_id must be a non-empty string, got {project_id!r}"
        )
    from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan as _prs  # noqa: PLC0415
    return _prs(project_id)


def probe_env_dependencies(*args, **kwargs):
    """Lazy proxy to bob3.environment_preflight.probe_dependencies — integration 18c33084."""
    from bob3.environment_preflight import probe_dependencies as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def spawn_workaround_agent(*args, **kwargs):
    """Lazy proxy to bob3.environment_preflight.spawn_workaround_agent — integration 18c33084."""
    from bob3.environment_preflight import spawn_workaround_agent as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def apply_workaround(*args, **kwargs):
    """Lazy proxy to bob3.environment_preflight.apply_workaround — integration 18c33084."""
    from bob3.environment_preflight import apply_workaround as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def run_environment_preflight(*args, **kwargs):
    """Lazy proxy to bob3.environment_preflight.run_preflight — integration 18c33084."""
    from bob3.environment_preflight import run_preflight as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def check_environment_capabilities(*args, **kwargs):
    """Lazy proxy to bob3.preflight.check_environment_capabilities — integration 64282372."""
    from bob3.preflight import check_environment_capabilities as _fn  # noqa: PLC0415
    return _fn(*args, **kwargs)


def defer_verifier_extension_features(
    feature_id: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation when its ACs target verifier internals.

    At feature-claim time (before the test-writer sub-agent runs), scans
    ``acceptance_criteria`` for any AC whose body contains a verifier path-token
    (``enhanced_verification``, paths ending in ``_verification.py`` or
    ``_verifier.py``) OR whose prefix is ``behavior:`` and references
    verifier-internal symbols.  When matched, updates the feature row to
    ``status='pending_successor_verify'`` and returns True so the orchestrator
    can skip sub-agent dispatch.

    This breaks the self-reference treadmill: the running verifier cannot
    validate behavior it does not yet implement.  Deferring these features
    hands off to the successor generation whose verifier already has the new
    code baked in.

    Args:
        feature_id:          UUID of the feature to potentially defer.
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was deferred (status set to
        ``'pending_successor_verify'``).  False when no verifier-self-reference
        was detected or when the DB update fails.

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    import logging
    from bob3 import db

    _logger = logging.getLogger(__name__)

    if not detect_pending_successor_verify(acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status="pending_successor_verify")
        _logger.info(
            "defer_verifier_extension_features: feature %s deferred to successor gen "
            "(AC references verifier internals)",
            feature_id,
        )
        return True
    except Exception:
        _logger.error(
            "defer_verifier_extension_features: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def export_database_path(db_path: pathlib.Path | None = None) -> pathlib.Path:
    """Return an absolute database path and set BOB3_DATABASE_PATH in the environment.

    Every orchestration entrypoint MUST call this once at startup so that all
    spawned sub-agents inherit the same resolved DB path regardless of cwd.

    Resolution order:
    1. ``db_path`` argument (explicit caller override)
    2. ``BOB3_DATABASE_PATH`` env var (already set by a parent orchestrator)
    3. ``cwd / bob3.db`` (default for the current working directory)

    The resolved path is exported as an absolute path into
    ``os.environ["BOB3_DATABASE_PATH"]`` so every subprocess and sub-agent
    that starts from this point will resolve the identical database file.

    Also logs the resolved path at INFO level so a mismatch is immediately
    visible in the run log.
    """
    import logging as _logging
    import os as _os
    from bob3.db import get_database_path as _get_db_path

    if db_path is not None:
        resolved = pathlib.Path(db_path).resolve()
    else:
        env_val = _os.environ.get("BOB3_DATABASE_PATH", "")
        if env_val:
            resolved = pathlib.Path(env_val).resolve()
        else:
            resolved = _get_db_path().resolve()

    _os.environ["BOB3_DATABASE_PATH"] = str(resolved)
    _logger = _logging.getLogger(__name__)
    _logger.info("export_database_path: resolved DB path = %s", resolved)
    return resolved


def get_orchestrator_dir() -> pathlib.Path:
    """Return the directory path of the orchestrator package."""
    return ORCHESTRATOR_DIR


def get_orchestrator_modules() -> list[str]:
    """Return names of Python modules in the orchestrator package directory.

    Scans the orchestrator package directory for .py files (excluding
    __init__.py and __pycache__) and returns their module names.
    """
    modules = []
    for py_file in sorted(ORCHESTRATOR_DIR.glob("*.py")):
        if py_file.name != "__init__.py":
            modules.append(py_file.stem)
    return modules

from bob3.meta_agent_selector import (  # noqa: F401 — integration 08e256ba
    select_spec_sections,
    run_focused_extraction,
)
from bob3.ac_form_validator import validate_acceptance_criteria  # noqa: F401 — integration bb0a01b2
from bob3.ac_artifact_verifier import verify_ac_artifacts, ArtifactMiss  # noqa: F401 — integration 7574e14c


def check_cost_enforcement(
    reported_cost,
    work_events,
    per_feature_ceiling,
    feature_id,
    exit_code=None,
    attempt_number=1,
):
    """Check budget enforcement for a sub-agent run that may have zero reported cost.

    When reported_cost is zero AND work_events > threshold, telemetry is considered
    lost. In that case the per-feature ceiling is charged and a structured
    cost_telemetry_lost WARN event is emitted. Budget enforcement is NEVER disabled
    solely because reported_cost==0.

    This is the primary entry point satisfying AC:
        Function defined: bob3.orchestrator.check_cost_enforcement

    Parameters
    ----------
    reported_cost:
        The raw cost from the SDK (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied when telemetry is lost.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).

    Returns
    -------
    EnforceBudgetResult
        ``.cost_to_charge`` is the amount to record; ``.telemetry_lost``
        indicates whether the pessimistic ceiling was applied.
    """
    from bob3.orchestrator.cost_telemetry_guard import enforce_budget_on_zero_cost as _fn  # noqa: PLC0415
    return _fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def classify_cost_telemetry(
    reported_cost,
    work_events,
):
    """Classify whether zero reported cost represents a telemetry loss or genuine free run.

    This function returns a string classification:
    - "telemetry_lost"  — cost==0 AND work_events > threshold (stream-json miss)
    - "free_retry"      — cost==0 AND work_events == 0 (genuine spawn crash, F-R7-478 path)
    - "normal"          — cost > 0 (telemetry was delivered correctly)

    Satisfies AC: Function defined: bob3.orchestrator.classify_cost_telemetry

    Parameters
    ----------
    reported_cost:
        The raw cost from the SDK. None coerced to 0.0. Negative treated as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.

    Returns
    -------
    str
        One of "telemetry_lost", "free_retry", or "normal".
    """
    from bob3.orchestrator.cost_telemetry_guard import is_cost_telemetry_lost as _is_lost  # noqa: PLC0415

    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0

    if cost > 0.0:
        return "normal"

    if _is_lost(reported_cost=reported_cost, work_events=work_events):
        return "telemetry_lost"

    return "free_retry"


def handle_gate_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace=None,
    synthesize_fn=None,
    score_gate_fn=None,
):
    """Re-synthesize ACs for a gate-blocked feature (one attempt per process).

    When a feature fails the spec_quality gate (composite < 0.85) it stays
    'pending'. The old loop re-dispatched it to test-writer/CodeT which rebuild
    CODE — but spec_quality is a function of the ACCEPTANCE CRITERIA, not code.
    Rebuilding code can never raise the score. This function is the correct
    recovery: regenerate ACs once via score_gate_loop + synthesize_for_feature.

    Bounded to ONE attempt per feature per process via bob75.orchestrator's
    _resynthesized_ids set. After one attempt, if the ACs still fail the gate,
    the feature is left blocked (needs_human) — no livelock.

    Satisfies AC: Function defined: bob3.orchestrator.handle_gate_blocked_feature

    Args:
        feature_id: Unique identifier of the gate-blocked feature (non-empty str).
        name: Feature name / title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier (passed through to synthesizer).
        workspace: Optional workspace path.
        synthesize_fn: Optional synthesizer override (defaults to bob3's).
        score_gate_fn: Optional score-gate-loop override (defaults to bob3's).

    Returns:
        (new_acs, new_composite) if re-synthesis produced new criteria, or
        (None, 0.0) if already attempted once or synthesis failed.

    Raises:
        ValueError: If feature_id is empty or not a string.
    """
    from bob73.gate_blocker import re_synthesize_gate_blocked_feature  # noqa: PLC0415
    return re_synthesize_gate_blocked_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        project_id=project_id,
        workspace=workspace,
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )


def defer_to_successor_generation(
    feature_id: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation when its ACs target verifier internals.

    At feature-claim time (before the test-writer sub-agent runs), scans
    ``acceptance_criteria`` for any AC whose body contains a verifier path-token
    OR whose prefix is ``behavior:`` and references verifier-internal symbols
    (``enhanced_verification``, ``verifier``, ``_check_criterion``, ``_demote_``).
    When matched, updates the feature row to ``status='pending_successor_verify'``
    and returns True so the orchestrator can skip sub-agent dispatch.

    This breaks the self-reference treadmill where verifier-extension features
    always fail in their own generation because the running verifier cannot
    validate patterns it does not yet implement. Deferring these features passes
    them to the successor generation whose verifier already has the new code.

    AC-mandated entry point for feature e3b15c8e.

    Args:
        feature_id:          UUID of the feature to potentially defer.
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was deferred (status set to
        ``'pending_successor_verify'``).  False when no verifier-self-reference
        was detected or when the DB update fails.

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    import logging
    from bob3 import db

    _logger = logging.getLogger(__name__)

    if not detect_pending_successor_verify(acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status="pending_successor_verify")
        _logger.info(
            "defer_to_successor_generation: feature %s deferred to successor gen "
            "(AC references verifier internals; subagent dispatch skipped)",
            feature_id,
        )
        return True
    except Exception:
        _logger.error(
            "defer_to_successor_generation: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


from bob3.orchestrator.gate_resynthesis import (  # noqa: F401,E402 — integration 066763fc
    resynthesized_ac_for_blocked_feature,
    mark_resynthesis_attempted,
)
from bob3.snapshot_pytest_config import enforce_maxfail_zero as enforce_snapshot_maxfail_zero  # noqa: F401 — integration 86105865
