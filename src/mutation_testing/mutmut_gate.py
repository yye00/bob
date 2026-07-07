"""mutation_testing.mutmut_gate — mutmut 3.x post-impl quality gate.

Wires mutmut 3.x as a verifier-stage quality gate. After pytest passes,
the impl files are mutated and the test suite re-run. The gate rejects when
``mutation_score < 0.75``. Surviving mutants are persisted to
``runs/<feature>/mutation_report.json`` so the next implementer attempt sees
them as "tests cannot distinguish your impl from these broken variants;
strengthen assertions."

Public API
----------
MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).

run_mutation_gate(feature_id, src_files, test_dir, workspace, pytest_passed, *, threshold=None) -> dict | None
    Run the mutmut post-impl quality gate. Returns None when skipped (pytest
    failed or empty feature_id), a gate-result dict on success, or a dict with
    ``skipped=True`` when mutmut is unavailable.

persist_surviving_mutants(report, workspace) -> Path
    Write ``runs/<feature>/mutation_report.json`` with unified-diff blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.mutmut_gate import (
    MUTATION_SCORE_THRESHOLD,
    run_mutation_tests,
)
from bob.verification.mutation_gate import (
    MutationReport,
    MutmutMissingError,
    persist_surviving_mutants,
)

__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "run_mutation_gate",
    "persist_surviving_mutants",
    "MutationReport",
    "MutmutMissingError",
]


def run_mutation_gate(
    feature_id: str,
    src_files: list[str | Path],
    test_dir: str | Path,
    workspace: str | Path,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Run the mutmut post-impl quality gate.

    Thin wrapper over :func:`bob.mutmut_gate.run_mutation_tests`. After pytest
    passes, mutates *src_files* and re-runs the test suite; rejects when the
    mutation score is below *threshold* (default 0.75). Surviving mutants are
    persisted to ``runs/<feature_id>/mutation_report.json``.

    Skips (returns None) when *pytest_passed* is False or *feature_id* is empty.
    Returns a dict with ``skipped=True`` when mutmut is not installed.

    Raises:
        TypeError:  When argument types are wrong.
        ValueError: When *threshold* is outside the [0.0, 1.0] range.
    """
    return run_mutation_tests(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )
