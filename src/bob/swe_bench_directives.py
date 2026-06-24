"""SWE-Bench cheap-win directives — thin re-export facade (F-R7-609).

All implementations live in bob.dispatch. This module provides a stable
import path that satisfies the "File exists: src/bob/swe_bench_directives.py"
AC without duplicating logic.
"""

from __future__ import annotations

from bob.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    apply_repro_test_directive,
    build_repo_tree,
    build_worker_system_prompt,
    check_mutation_pass,
    compute_adaptive_edit_mode,
    compute_edit_mode,
    emit_edit_mode_event,
    emit_weak_test_event,
    handle_mutation_failure,
    inject_failing_repro_test_directive,
    inject_repo_tree,
    inject_repo_tree_into_prompt,
    inject_repo_tree_to_worker,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
    validate_repo_tree,
)

__all__ = [
    "EditModeDecision",
    "apply_cheap_wins",
    "apply_repro_test_directive",
    "build_repo_tree",
    "build_worker_system_prompt",
    "check_mutation_pass",
    "compute_adaptive_edit_mode",
    "compute_edit_mode",
    "emit_edit_mode_event",
    "emit_weak_test_event",
    "handle_mutation_failure",
    "inject_failing_repro_test_directive",
    "inject_repo_tree",
    "inject_repo_tree_into_prompt",
    "inject_repo_tree_to_worker",
    "run_mutation_pass_check",
    "select_edit_mode",
    "should_inject_repro_test_directive",
    "validate_repo_tree",
]
