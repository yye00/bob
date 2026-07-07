"""SWE-Bench cheap wins — AC-named façade over :mod:`bob.dispatch` (F-R7-609).

Four leaderboard-validated brownfield directives that cost <5% complexity and
add measurable accuracy, synthesised from Anthropic's SWE-Bench scaffold,
Agentless 1.5, SWE-Edit (NeurIPS 2025) and the ICSE 2026 false-pass study:

    (A) Repo tree in the worker system prompt   -> :func:`build_repo_tree`
    (B) "Write a failing repro test first"       -> injected via dispatch
    (C) Adaptive edit mode (replace vs rewrite)  -> :func:`select_edit_mode`
    (D) Mutation-pass check (weak-test detector) -> :func:`mutation_pass_check`

The canonical implementations live in :mod:`bob.dispatch`, wired through the
worker-spawn path. This module simply re-exports the AC-named entry points so
they resolve on ``bob.swe_bench_cheap_wins`` as required by the feature ACs.
"""

from __future__ import annotations

from bob.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    build_repo_tree,
    build_worker_system_prompt,
    check_mutation_pass,
    compute_edit_metrics,
    compute_edit_mode,
    emit_edit_mode_event,
    emit_weak_test_event,
    inject_failing_repro_test_directive,
    inject_repo_tree_into_prompt,
    mutation_pass_check,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)

__all__ = [
    "EditModeDecision",
    "apply_cheap_wins",
    "build_repo_tree",
    "build_worker_system_prompt",
    "check_mutation_pass",
    "compute_edit_metrics",
    "compute_edit_mode",
    "emit_edit_mode_event",
    "emit_weak_test_event",
    "inject_failing_repro_test_directive",
    "inject_repo_tree_into_prompt",
    "mutation_pass_check",
    "run_mutation_pass_check",
    "select_edit_mode",
    "should_inject_repro_test_directive",
]
