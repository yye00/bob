"""bob.mutation_testing — public API for the mutmut post-impl quality gate.

This package is the canonical entry-point for running mutation tests as a
verifier-stage quality gate. It delegates to
``bob.verification.mutation_gate`` for the actual mutmut execution and
to ``bob.mutation_testing_post_impl_quality_gate_mutmut`` for the gate
facade.

Public API
----------
MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).

run_mutmut_gate(feature_id, src_files, test_dir, workspace,
                pytest_passed, *, threshold=None) -> dict | None
    Run the mutmut quality gate. Returns None when the gate is skipped
    (pytest failed or empty feature_id), a gate-result dict on success,
    or a dict with skipped=True when mutmut is unavailable.

persist_mutation_report(report, workspace) -> Path
    Persist surviving mutant diffs to runs/<feature_id>/mutation_report.json.

run_mutation_suite(feature_id, src_files, test_dir, workspace,
                   pytest_passed, *, threshold=None) -> dict | None
    Alias for run_mutmut_gate.

compute_mutation_score(killed, total) -> float
    Compute the mutation score from killed/total mutant counts.

run_mutation_tests(feature_id, src_files, test_dir, workspace,
                   pytest_passed, *, threshold=None) -> dict | None
    Alias for run_mutmut_gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.mutation_testing.mutmut_verifier import (
    MUTATION_SCORE_THRESHOLD,
    check_mutation_score,
)
from bob.mutation_testing_post_impl_quality_gate_mutmut import (
    mutation_testing_post_impl_quality_gate_mutmut as _gate,
)
from bob.verification.mutation_gate import (
    MutationReport,
    persist_surviving_mutants as _persist_surviving_mutants,
)


def run_mutmut_gate(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Run the mutmut post-impl quality gate.

    After pytest passes, mutates *src_files* and re-runs the test suite.
    Rejects if mutation_score < threshold (default 0.75). Surviving mutants
    are persisted to runs/<feature_id>/mutation_report.json.

    Returns None when skipped (pytest failed or empty feature_id), a gate-result
    dict on success, or a dict with skipped=True when mutmut is unavailable.
    """
    return _gate(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )


def persist_mutation_report(
    report: MutationReport,
    workspace: str | Path,
) -> Path:
    """Persist surviving mutant diffs to runs/<feature_id>/mutation_report.json.

    Args:
        report:    MutationReport produced by run_mutation_test.
        workspace: Project workspace root.

    Returns:
        Path to the written mutation_report.json file.
    """
    return _persist_surviving_mutants(report, workspace)


def compute_mutation_score(killed: int, total: int) -> float:
    """Compute the mutation score from killed and total mutant counts.

    Returns killed / total, or 1.0 when total is 0 (no mutants generated).

    Args:
        killed: Number of mutants killed by the test suite.
        total:  Total number of mutants generated.

    Returns:
        Mutation score in [0.0, 1.0].

    Raises:
        ValueError: When killed or total is negative, or killed > total.
        TypeError:  When killed or total is not an integer.
    """
    if not isinstance(killed, int):
        raise TypeError(f"killed must be an int, got {type(killed).__name__!r}")
    if not isinstance(total, int):
        raise TypeError(f"total must be an int, got {type(total).__name__!r}")
    if killed < 0:
        raise ValueError(f"killed must be non-negative, got {killed!r}")
    if total < 0:
        raise ValueError(f"total must be non-negative, got {total!r}")
    if killed > total:
        raise ValueError(
            f"killed ({killed}) cannot exceed total ({total})"
        )
    if total == 0:
        return 1.0
    return killed / total


def run_mutation_suite(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Alias for run_mutmut_gate."""
    return run_mutmut_gate(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )


def run_mutation_tests(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Alias for run_mutmut_gate for backwards compatibility."""
    return run_mutmut_gate(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )


__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "MutationReport",
    "check_mutation_score",
    "compute_mutation_score",
    "persist_mutation_report",
    "run_mutmut_gate",
    "run_mutation_suite",
    "run_mutation_tests",
]
