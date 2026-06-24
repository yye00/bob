"""bob3.mutation_gate — high-level mutation testing quality gate for the verifier stage.

Wires mutmut 3.x as a verifier-stage quality gate.  After pytest passes,
mutates impl files and re-runs the test suite.  Rejects if
mutation_score < 0.75.  Surviving mutants are persisted to
runs/<feature>/mutation_report.json so the next implementer attempt sees
"tests cannot distinguish your impl from these broken variants; strengthen
assertions."

Public API
----------
MUTATION_SCORE_THRESHOLD : float
    Default gate threshold (0.75).

run_mutation_testing(feature_id, src_files, test_dir, workspace,
                     pytest_passed, *, threshold=None) -> dict | None
    Run the mutmut quality gate. Returns None when skipped (pytest failed
    or empty feature_id), a gate-result dict on success, or a dict with
    skipped=True when mutmut is unavailable.

check_mutation_score(score, threshold=None) -> bool
    Return True when score >= threshold (default 0.75). Pure predicate.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from bob3.verification.mutation_gate import (
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

logger = logging.getLogger(__name__)

MUTATION_SCORE_THRESHOLD: float = 0.75

__all__ = [
    "MUTATION_SCORE_THRESHOLD",
    "check_mutation_score",
    "compute_mutation_score",
    "run_mutation_testing",
    "run_mutation_tests",
    "MutationReport",
    "MutmutMissingError",
    "default_threshold",
    "mutation_operators",
    "never_mutates_failing_impl",
    "passes_gate",
    "persist_surviving_mutants",
    "run_mutation_test",
    "runs_only_after_pytest_pass",
]


def check_mutation_score(score: float, threshold: float | None = None) -> bool:
    """Return True when *score* meets or exceeds the gate threshold.

    Args:
        score:     Mutation score in [0.0, 1.0]. Values outside this range
                   raise ValueError.
        threshold: Override the default 0.75 threshold.

    Returns:
        True when score >= threshold, False otherwise.

    Raises:
        TypeError:  When score or threshold is not a number.
        ValueError: When score or threshold is outside [0.0, 1.0].
    """
    if not isinstance(score, (int, float)):
        raise TypeError(f"score must be a float, got {type(score).__name__!r}")
    if score < 0.0 or score > 1.0:
        raise ValueError(f"score must be between 0.0 and 1.0, got {score!r}")
    if threshold is not None:
        if not isinstance(threshold, (int, float)):
            raise TypeError(
                f"threshold must be a float, got {type(threshold).__name__!r}"
            )
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError(
                f"threshold must be between 0.0 and 1.0, got {threshold!r}"
            )
    return passes_gate(score, threshold)


def run_mutation_testing(
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

    Skips (returns None) when *pytest_passed* is False or *feature_id* is
    empty. Returns a dict with ``skipped=True`` when mutmut is not installed.

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
        TypeError:  When argument types are wrong.
        ValueError: When threshold is out of [0.0, 1.0] range.
    """
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

    passed = check_mutation_score(report.mutation_score, effective_threshold)

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


def run_mutation_tests(
    feature_id: str,
    src_files: list,
    test_dir,
    workspace,
    pytest_passed: bool,
    *,
    threshold: float | None = None,
) -> dict | None:
    """Alias for run_mutation_testing — AC: Function defined: bob3.mutation_gate.run_mutation_tests."""
    return run_mutation_testing(
        feature_id=feature_id,
        src_files=src_files,
        test_dir=test_dir,
        workspace=workspace,
        pytest_passed=pytest_passed,
        threshold=threshold,
    )


def compute_mutation_score(killed: int, total: int) -> float:
    """Compute mutation score as killed/total.

    AC: Function defined: bob3.mutation_gate.compute_mutation_score.

    Args:
        killed: Number of mutants killed by the test suite.
        total:  Total number of mutants generated.

    Returns:
        Float in [0.0, 1.0]. Returns 1.0 when total is 0 (no mutants generated).

    Raises:
        TypeError:  When killed or total is not an int.
        ValueError: When killed < 0, total < 0, or killed > total.
    """
    if not isinstance(killed, int):
        raise TypeError(f"killed must be an int, got {type(killed).__name__!r}")
    if not isinstance(total, int):
        raise TypeError(f"total must be an int, got {type(total).__name__!r}")
    if killed < 0:
        raise ValueError(f"killed must be >= 0, got {killed!r}")
    if total < 0:
        raise ValueError(f"total must be >= 0, got {total!r}")
    if killed > total:
        raise ValueError(f"killed ({killed}) cannot exceed total ({total})")
    if total == 0:
        return 1.0
    return killed / total
