"""bob3.mutation_testing — public API for the mutmut post-impl quality gate.

This module is the canonical entry-point for running mutation tests as a
verifier-stage quality gate. It delegates to
``bob3.verification.mutation_gate`` for the actual mutmut execution and
to ``bob3.mutation_testing_post_impl_quality_gate_mutmut`` for the gate
facade.

Public API
----------
MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).

run_mutation_tests(feature_id, src_files, test_dir, workspace,
                   pytest_passed, *, threshold=None) -> dict | None
    Run the mutmut quality gate. Returns None when the gate is skipped
    (pytest failed or empty feature_id), a gate-result dict on success,
    or a dict with skipped=True when mutmut is unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.mutation_testing_post_impl_quality_gate_mutmut import (
    MUTATION_SCORE_THRESHOLD,
    mutation_testing_post_impl_quality_gate_mutmut,
)

__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "run_mutation_tests",
]


def run_mutation_tests(
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

    Skips (returns None) when *pytest_passed* is False or *feature_id* is empty.
    Returns a dict with ``skipped=True`` when mutmut is not installed.

    Args:
        feature_id:    Unique feature identifier.
        src_files:     Source files to mutate.
        test_dir:      Test directory to run against mutants.
        workspace:     Project workspace root.
        pytest_passed: Whether the pytest suite passed before calling the gate.
        threshold:     Override the default 0.75 mutation-score threshold.

    Returns:
        None when skipped; otherwise a dict containing at minimum:
        - ``passed`` (bool)
        - ``mutation_score`` (float)
        - ``feature_id`` (str)
        or on mutmut-missing:
        - ``skipped`` (bool, True)
        - ``reason`` (str)

    Raises:
        TypeError: When argument types are wrong.
        ValueError: When threshold is out of [0.0, 1.0] range.
    """
    return mutation_testing_post_impl_quality_gate_mutmut(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )
