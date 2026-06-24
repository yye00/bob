"""bob73.mutation_gate — thin shim exposing bob mutation gate via bob73 namespace.

Wraps ``bob.verification.mutation_gate`` so that the bob73 package
satisfies the AC: ``Function defined: bob73.mutation_gate.run_mutation_test``.

Public API
----------
run_mutation_test(feature_id, src_files, test_dir, workspace, time_limit_sec=180) -> MutationReport
    Run mutmut on src_files, return a MutationReport.

MutationReport
    Dataclass: feature_id, total_mutants, killed, survived, timed_out,
    mutation_score, surviving_mutant_diffs, timed_out_early, partial.

passes_gate(score, threshold=None) -> bool
    Return True when score >= threshold (default 0.75).

persist_surviving_mutants(report, workspace) -> Path
    Write runs/<feature>/mutation_report.json with unified-diff blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.verification.mutation_gate import (
    MutationReport,
    MutmutMissingError,
    default_threshold,
    enforce_time_limit,
    handle_mutmut_unavailable,
    mutation_operators,
    never_mutates_failing_impl,
    passes_gate,
    persist_surviving_mutants,
    return_feature_to_ready_on_failure,
    run_mutation_test,
    runs_only_after_pytest_pass,
)

__all__ = [
    "MutationReport",
    "MutmutMissingError",
    "default_threshold",
    "enforce_time_limit",
    "handle_mutmut_unavailable",
    "mutation_operators",
    "never_mutates_failing_impl",
    "passes_gate",
    "persist_surviving_mutants",
    "return_feature_to_ready_on_failure",
    "run_mutation_test",
    "runs_only_after_pytest_pass",
]
