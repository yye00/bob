"""bob.mutmut_verifier — verify_mutation_score entry-point for the mutmut gate.

This module provides the ``verify_mutation_score`` function, which is the
canonical entry-point for the verifier stage.  It delegates to
``bob.verification.mutation_gate`` for the actual mutmut execution.

Public API
----------
verify_mutation_score(feature_id, src_files, test_dir, workspace,
                      pytest_passed, *, threshold=None) -> dict | None
    Run the mutation gate and return the gate result dict, or None when skipped.

MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.mutation_testing_post_impl_quality_gate_mutmut import (
    MUTATION_SCORE_THRESHOLD,
    mutation_testing_post_impl_quality_gate_mutmut,
)
from bob.verification.mutation_gate import (
    MutationReport,
    MutmutMissingError,
    default_threshold,
    mutation_operators,
    never_mutates_failing_impl,
    passes_gate,
    persist_surviving_mutants,
    run_mutation_test,
    runs_only_after_pytest_pass,
)

__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "verify_mutation_score",
    "MutationReport",
    "MutmutMissingError",
    "passes_gate",
    "persist_surviving_mutants",
    "default_threshold",
    "mutation_operators",
    "runs_only_after_pytest_pass",
    "never_mutates_failing_impl",
    "run_mutation_test",
]


def verify_mutation_score(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Run the mutmut post-impl quality gate.

    This is the verifier-stage entry-point.  It delegates to
    ``mutation_testing_post_impl_quality_gate_mutmut`` which calls mutmut,
    collects surviving mutants, and persists the report.

    Returns None when the gate is skipped (pytest failed, empty feature_id).
    Returns a dict with ``passed``, ``mutation_score``, etc. on success.
    Returns a dict with ``skipped=True`` when mutmut is unavailable.

    Raises TypeError for wrong argument types and ValueError for out-of-range
    threshold values.
    """
    return mutation_testing_post_impl_quality_gate_mutmut(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )
