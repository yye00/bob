"""CodeT mutual-agreement triangulation — KxK code-test matrix.

Public API for the CodeT pattern (ICLR 2023) combined with TestGen-LLM's
Build/Pass/Coverage triple filter.  Exposes two entry points:

    spawn_k_candidates(feature_id, acceptance_criteria, K, workspace)
        → (impls, test_sets)

    mutual_agreement_score(impls, test_sets, workspace)
        → ScoredMatrix

Both delegate to bob.orchestrator.codet_triangulation for the heavy lifting.
This module exists as the stable, importable entry point required by the
integration AC (bob.codet_matrix.*).

Integration hook: importing bob.orchestrator triggers the codet_triangulation
module to be available via bob.orchestrator.codet_triangulation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bob.orchestrator.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    NoCandidatesError,
    ScoredMatrix,
    TripleFilterResult,
    archive_losers,
    persist_winning_cell,
    score_matrix,
    spawn_k_impls,
    spawn_k_tests,
    triple_filter,
)

__all__ = [
    "mutual_agreement_score",
    "mutual_agreement_triangulation",
    "score_kxk_matrix",
    "spawn_candidate_impls",
    "spawn_candidate_tests",
    "spawn_k_candidates",
    "spawn_kxk_matrix",
    # Re-exported data classes
    "CandidateImpl",
    "CandidateTestSet",
    "MatrixCell",
    "NoCandidatesError",
    "ScoredMatrix",
    "TripleFilterResult",
    # Lower-level helpers available for power users
    "archive_losers",
    "persist_winning_cell",
    "score_matrix",
    "spawn_k_impls",
    "spawn_k_tests",
    "triple_filter",
]


def spawn_k_candidates(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> tuple[list[CandidateImpl], list[CandidateTestSet]]:
    """Spawn K candidate implementations and K candidate test sets.

    Combines spawn_k_impls and spawn_k_tests into a single convenience call,
    producing the inputs needed by mutual_agreement_score.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings that guide generation.
        K: Number of candidates for each side of the matrix. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        A 2-tuple ``(impls, test_sets)`` where both lists have length K.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")

    impls = spawn_k_impls(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
    test_sets = spawn_k_tests(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
    return impls, test_sets


def mutual_agreement_triangulation(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Run the full CodeT mutual-agreement triangulation pipeline end-to-end.

    Spawns K candidate implementations and K candidate test sets, scores the
    resulting KxK matrix by mutual agreement, and returns the scored matrix
    with the winning (impl, test) pair identified.

    This is the primary high-level entry point for the CodeT triangulation
    pattern (ICLR 2023). For fine-grained control, use spawn_k_candidates
    and mutual_agreement_score separately.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings guiding candidate generation.
        K: Number of candidates for each side of the matrix. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix identifying the winning (impl, test) pair and all scores.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")

    impls, test_sets = spawn_k_candidates(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
    return score_matrix(impls, test_sets, workspace=workspace)


def score_kxk_matrix(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement.

    This is an alias for ``mutual_agreement_score`` with a name that
    explicitly surfaces the KxK structure described in CodeT (ICLR 2023).

    For each (impl_i, test_j) cell:
        score = passing_tests * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail test set j, measuring the test set's discriminative power.

    Args:
        impls: Candidate implementations from spawn_k_candidates or spawn_k_impls.
        test_sets: Candidate test sets from spawn_k_candidates or spawn_k_tests.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix with all cells scored and winner identified.

    Raises:
        ValueError: If either list is empty.
    """
    return mutual_agreement_score(impls, test_sets, workspace=workspace)


def spawn_kxk_matrix(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Spawn K candidates and score the full KxK mutual-agreement matrix.

    Convenience wrapper that combines spawn_k_candidates and
    mutual_agreement_score into a single call.  Equivalent to calling::

        impls, test_sets = spawn_k_candidates(feature_id, acs, K, workspace)
        return mutual_agreement_score(impls, test_sets, workspace)

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings guiding candidate generation.
        K: Number of candidates for each side of the matrix. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix identifying the winning (impl, test) pair and all scores.

    Raises:
        ValueError: If K < 1.
    """
    impls, test_sets = spawn_k_candidates(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
    return mutual_agreement_score(impls, test_sets, workspace=workspace)


def mutual_agreement_score(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score each (impl, test) cell of the KxK matrix by mutual agreement.

    Mutual-agreement score for cell (i, j):
        score = passing_tests_i_j * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail test set j — measuring the test set's discriminative power.

    The winner is the cell with the highest score.

    Args:
        impls: Candidate implementations from spawn_k_candidates or spawn_k_impls.
        test_sets: Candidate test sets from spawn_k_candidates or spawn_k_tests.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix identifying the winning (impl, test) pair and all scores.

    Raises:
        ValueError: If either list is empty.
    """
    if not impls:
        raise ValueError("impls must not be empty")
    if not test_sets:
        raise ValueError("test_sets must not be empty")

    return score_matrix(impls, test_sets, workspace=workspace)


# ---------------------------------------------------------------------------
# AC-required aliases
# ---------------------------------------------------------------------------

def spawn_candidate_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateTestSet]:
    """Alias for spawn_k_tests required by the feature AC.

    Args:
        feature_id: The feature being tested.
        acceptance_criteria: List of AC strings to build tests from.
        K: Number of candidate test sets to produce. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateTestSet objects, length K.
    """
    return spawn_k_tests(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )


def spawn_candidate_impls(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateImpl]:
    """Alias for spawn_k_impls required by the feature AC.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings guiding generation.
        K: Number of candidate implementations to produce. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateImpl objects, length K.
    """
    return spawn_k_impls(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
