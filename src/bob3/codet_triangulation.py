"""CodeT mutual-agreement triangulation — public entry point.

Implements the CodeT pattern (ICLR 2023) combined with TestGen-LLM's
Build/Pass/Coverage triple filter.  Exposes two primary functions:

    generate_kxk_matrix(impls, test_sets)
        → ScoredMatrix

    mutual_agreement_scorer(impl, test_set, all_impls, all_test_sets)
        → MatrixCell

Source: Agent 4 Section 9 (CodeT, ICLR 2023; TestGen-LLM).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from bob3.orchestrator.codet_triangulation import (
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
    "generate_kxk_matrix",
    "generate_k_candidates",
    "mutual_agreement_scorer",
    # AC-required aliases
    "score_mutual_agreement",
    "score_kxk_matrix",
    "spawn_candidate_tests",
    "spawn_candidate_implementations",
    "spawn_candidate_impls",
    # Re-exported types for convenience
    "CandidateImpl",
    "CandidateTestSet",
    "MatrixCell",
    "NoCandidatesError",
    "ScoredMatrix",
    "TripleFilterResult",
    "archive_losers",
    "persist_winning_cell",
    "score_matrix",
    "spawn_k_impls",
    "spawn_k_tests",
    "triple_filter",
]


def generate_kxk_matrix(
    impls: Sequence[CandidateImpl],
    test_sets: Sequence[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    For each (impl_i, test_j) cell:
        score = passing_tests * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail test set j, measuring the test set's discriminative power.

    The winner is the cell with the highest mutual-agreement score.

    Args:
        impls: Candidate implementations (from spawn_k_impls or equivalent).
        test_sets: Candidate test sets (from spawn_k_tests or equivalent).
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix with all cells scored and the winning cell identified.

    Raises:
        ValueError: If either impls or test_sets is empty.
    """
    impls_list = list(impls)
    test_sets_list = list(test_sets)

    if not impls_list:
        raise ValueError("impls must not be empty")
    if not test_sets_list:
        raise ValueError("test_sets must not be empty")

    return score_matrix(impls_list, test_sets_list, workspace=workspace)


def mutual_agreement_scorer(
    impl: CandidateImpl,
    test_set: CandidateTestSet,
    all_impls: Sequence[CandidateImpl],
    all_test_sets: Sequence[CandidateTestSet],
    workspace: str | Path | None = None,
) -> MatrixCell:
    """Compute the mutual-agreement score for a single (impl, test) cell.

    The mutual-agreement score (CodeT, ICLR 2023):
        score = passing_tests * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail the given test set.  The ``+1`` prevents zero-score from passing
    tests that fail no other implementation (vacuous tests).

    Args:
        impl: The candidate implementation to score.
        test_set: The candidate test set to score against.
        all_impls: All candidate implementations (needed to compute
            unique_fail_count across the full matrix).
        all_test_sets: All candidate test sets (for context; not directly
            used in single-cell scoring but passed for API completeness).
        workspace: Project root directory (defaults to cwd).

    Returns:
        MatrixCell with the score for this (impl, test) pair.

    Raises:
        ValueError: If all_impls is empty.
    """
    all_impls_list = list(all_impls)
    if not all_impls_list:
        raise ValueError("all_impls must not be empty")

    # Score the full matrix to get cross-impl context, then extract the cell.
    all_test_sets_list = list(all_test_sets) if all_test_sets else [test_set]

    # Ensure impl and test_set are in the lists (needed for matrix scoring)
    if impl not in all_impls_list:
        all_impls_list = [impl] + all_impls_list
    if test_set not in all_test_sets_list:
        all_test_sets_list = [test_set] + all_test_sets_list

    matrix = score_matrix(all_impls_list, all_test_sets_list, workspace=workspace)

    # Find the cell for this specific (impl, test) pair
    for cell in matrix.cells:
        if (all_impls_list[cell.impl_index] is impl
                and all_test_sets_list[cell.test_index] is test_set):
            return cell

    # Fallback: match by index if identity check missed (shouldn't happen)
    target_impl_idx = all_impls_list.index(impl)
    target_test_idx = all_test_sets_list.index(test_set)
    for cell in matrix.cells:
        if cell.impl_index == target_impl_idx and cell.test_index == target_test_idx:
            return cell

    raise RuntimeError(
        f"Cell for impl[{impl.index}] x test[{test_set.index}] not found in matrix"
    )


# ---------------------------------------------------------------------------
# AC-required name aliases
# The acceptance criteria for F-R7-454 require these specific function names.
# ---------------------------------------------------------------------------


def score_kxk_matrix(
    impls: Sequence[CandidateImpl],
    test_sets: Sequence[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    Alias for generate_kxk_matrix — satisfies AC: Function defined:
    bob3.codet_triangulation.score_kxk_matrix.

    Args:
        impls: Candidate implementations.
        test_sets: Candidate test sets.
        workspace: Project root directory.

    Returns:
        ScoredMatrix with all cells scored and winner identified.

    Raises:
        ValueError: If either impls or test_sets is empty.
    """
    return generate_kxk_matrix(impls, test_sets, workspace=workspace)


def generate_k_candidates(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> tuple[list[CandidateImpl], list[CandidateTestSet]]:
    """Generate K candidate implementations and K candidate test sets.

    Convenience entry point for the CodeT (ICLR 2023) pattern: spawns both
    candidate impls and candidate test sets in one call, ready for
    generate_kxk_matrix.

    Args:
        feature_id: The feature being tested.
        acceptance_criteria: List of AC strings.
        K: Number of candidates of each kind. Must be >= 1.
        workspace: Project root directory.

    Returns:
        Tuple of (impls, test_sets), each a list of length K.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError(f"K must be >= 1, got {K}")
    impls = spawn_k_impls(feature_id, acceptance_criteria, K=K, workspace=workspace)
    test_sets = spawn_k_tests(feature_id, acceptance_criteria, K=K, workspace=workspace)
    return impls, test_sets


def spawn_candidate_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateTestSet]:
    """Generate K candidate test sets (CodeT ICLR 2023 pattern).

    Alias for spawn_k_tests — satisfies AC: Function defined:
    bob3.codet_triangulation.spawn_candidate_tests.

    Args:
        feature_id: The feature being tested.
        acceptance_criteria: List of AC strings.
        K: Number of candidate test sets. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateTestSet objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    return spawn_k_tests(feature_id, acceptance_criteria, K=K, workspace=workspace)


def spawn_candidate_impls(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 2,
    workspace: str | Path | None = None,
) -> list[CandidateImpl]:
    """Generate K candidate implementations (CodeT ICLR 2023 pattern).

    Alias for spawn_k_impls — satisfies AC: Function defined:
    bob3.codet_triangulation.spawn_candidate_impls.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings.
        K: Number of candidate implementations. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateImpl objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    return spawn_k_impls(feature_id, acceptance_criteria, K=K, workspace=workspace)


def spawn_candidate_implementations(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 2,
    workspace: str | Path | None = None,
) -> list[CandidateImpl]:
    """Generate K candidate implementations (CodeT ICLR 2023 pattern).

    AC-required alias for spawn_k_impls — satisfies AC: Function defined:
    bob3.codet_triangulation.spawn_candidate_implementations.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings.
        K: Number of candidate implementations. Must be >= 1.
        workspace: Project root directory.

    Returns:
        List of CandidateImpl objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    return spawn_k_impls(feature_id, acceptance_criteria, K=K, workspace=workspace)


def score_mutual_agreement(
    impl: CandidateImpl,
    test_set: CandidateTestSet,
    all_impls: Sequence[CandidateImpl],
    all_test_sets: Sequence[CandidateTestSet],
    workspace: str | Path | None = None,
) -> MatrixCell:
    """Compute the mutual-agreement score for a single (impl, test) cell.

    AC-required alias for mutual_agreement_scorer — satisfies AC: Function
    defined: bob3.codet_triangulation.score_mutual_agreement.

    Args:
        impl: The candidate implementation to score.
        test_set: The candidate test set to score against.
        all_impls: All candidate implementations.
        all_test_sets: All candidate test sets.
        workspace: Project root directory.

    Returns:
        MatrixCell with the score for this (impl, test) pair.

    Raises:
        ValueError: If all_impls is empty.
    """
    return mutual_agreement_scorer(impl, test_set, all_impls, all_test_sets, workspace=workspace)
