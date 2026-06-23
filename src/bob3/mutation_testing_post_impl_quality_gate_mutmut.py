"""mutation_testing_post_impl_quality_gate_mutmut — mutmut post-impl quality gate facade.

Wires mutmut 3.x as a verifier-stage quality gate.  After pytest passes,
mutate the impl files and re-run the test suite.  Rejects if
mutation_score < 0.75.  Surviving mutants are persisted to
runs/<feature>/mutation_report.json; the next implementer attempt sees them
as "tests cannot distinguish your impl from these broken variants; strengthen
assertions."

Public API
----------
MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).

mutation_testing_post_impl_quality_gate_mutmut(feature_id, src_files, test_dir, workspace, pytest_passed, *, threshold=None) -> dict | None
    Run the mutation gate.  Returns None when the gate is skipped (pytest
    failed or empty feature_id), a dict with passed/mutation_score on
    success, or a dict with skipped=True/reason when mutmut is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from bob3.verification.mutation_gate import (
    MutationReport,
    MutmutMissingError,
    passes_gate,
    persist_surviving_mutants,
    run_mutation_test,
)

logger = logging.getLogger(__name__)

MUTATION_SCORE_THRESHOLD: float = 0.75

__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "mutation_testing_post_impl_quality_gate_mutmut",
]


def mutation_testing_post_impl_quality_gate_mutmut(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Run the mutmut post-impl quality gate.

    Skips (returns None) when *pytest_passed* is False or *feature_id* is
    empty.  Returns a dict describing the gate outcome, or a dict with
    ``skipped=True`` when mutmut is not installed.

    Args:
        feature_id:    Unique feature identifier.
        src_files:     Source files to mutate.
        test_dir:      Test directory to run against mutants.
        workspace:     Project workspace root.
        pytest_passed: Whether the pytest suite passed before calling the gate.
        threshold:     Override the default 0.75 mutation-score threshold.

    Returns:
        None when skipped; otherwise a dict with at minimum:
        - ``passed`` (bool)
        - ``mutation_score`` (float)
        - ``feature_id`` (str)
        or on mutmut-missing:
        - ``skipped`` (bool, True)
        - ``reason`` (str)
    """
    # Validate types — raise TypeError/ValueError on invalid inputs
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__!r}")
    if not isinstance(src_files, list):
        raise TypeError(f"src_files must be a list, got {type(src_files).__name__!r}")
    if not isinstance(pytest_passed, bool):
        raise TypeError(
            f"pytest_passed must be a bool, got {type(pytest_passed).__name__!r}"
        )
    if threshold is not None:
        if not isinstance(threshold, (int, float)):
            raise TypeError(
                f"threshold must be a float, got {type(threshold).__name__!r}"
            )
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError(
                f"threshold must be between 0.0 and 1.0, got {threshold!r}"
            )

    if not feature_id or not pytest_passed:
        return None

    effective_threshold = threshold if threshold is not None else MUTATION_SCORE_THRESHOLD

    try:
        report: MutationReport = run_mutation_test(
            feature_id=feature_id,
            src_files=src_files,
            test_dir=test_dir,
            workspace=workspace,
        )
    except MutmutMissingError as exc:
        logger.warning("mutmut unavailable; skipping mutation gate: %s", exc)
        return {"skipped": True, "reason": f"mutmut not available: {exc}"}

    passed = passes_gate(report.mutation_score, effective_threshold)

    if not passed:
        persist_surviving_mutants(report, workspace)

    return {
        "passed": passed,
        "mutation_score": report.mutation_score,
        "feature_id": feature_id,
        "total_mutants": report.total_mutants,
        "killed": report.killed,
        "survived": report.survived,
        "timed_out": report.timed_out,
        "timed_out_early": report.timed_out_early,
        "partial": report.partial,
        "threshold": effective_threshold,
    }
