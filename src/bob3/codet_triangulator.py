"""CodeT mutual-agreement triangulation — codet_triangulator public API.

Exposes the KxK code-test matrix scoring strategy from CodeT (ICLR 2023)
combined with TestGen-LLM's Build/Pass/Coverage triple filter through a
focused two-function API:

    triangulate_kxk_matrix(impls, test_sets, workspace)
        → ScoredMatrix

    score_mutual_agreement(impl, test_set, all_impls, all_test_sets, workspace)
        → MatrixCell

This module exists as the canonical, AC-required entry point for the
CodeT triangulation feature (F-R7-454).  The heavy lifting is delegated to
``bob3.orchestrator.codet_triangulation``.

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
    "triangulate_kxk_matrix",
    "score_mutual_agreement",
    # AC-required function names
    "score_kxk_matrix",
    "spawn_candidate_tests",
    "spawn_candidate_implementations",
    # Re-exported types for convenience
    "CandidateImpl",
    "CandidateTestSet",
    "MatrixCell",
    "NoCandidatesError",
    "ScoredMatrix",
    "TripleFilterResult",
    "archive_losers",
    "persist_winning_cell",
    "spawn_k_impls",
    "spawn_k_tests",
    "triple_filter",
]


def triangulate_kxk_matrix(
    impls: Sequence[CandidateImpl],
    test_sets: Sequence[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    For each (impl_i, test_j) cell the mutual-agreement score is:
        score = passing_tests * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail test set j — measuring the test set's discriminative power.  The
    ``+1`` prevents zero-score from passing tests that fail no other
    implementation (vacuous tests).

    The winner is the cell with the highest mutual-agreement score.  Combined
    with TestGen-LLM's Build/Pass/Coverage triple filter this is the cheapest
    known guard against AI-judge sycophancy.

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


def score_mutual_agreement(
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
    fail the given test set.

    Args:
        impl: The candidate implementation to score.
        test_set: The candidate test set to score against.
        all_impls: All candidate implementations (needed to compute
            unique_fail_count across the full matrix).  Must not be empty.
        all_test_sets: All candidate test sets (for context).  If empty,
            falls back to a list containing only ``test_set``.
        workspace: Project root directory (defaults to cwd).

    Returns:
        MatrixCell with the mutual-agreement score for this (impl, test) pair.

    Raises:
        ValueError: If all_impls is empty.
    """
    all_impls_list = list(all_impls)
    if not all_impls_list:
        raise ValueError("all_impls must not be empty")

    all_test_sets_list = list(all_test_sets) if all_test_sets else [test_set]

    # Ensure impl and test_set are present (required for cross-impl scoring)
    if impl not in all_impls_list:
        all_impls_list = [impl] + all_impls_list
    if test_set not in all_test_sets_list:
        all_test_sets_list = [test_set] + all_test_sets_list

    matrix = score_matrix(all_impls_list, all_test_sets_list, workspace=workspace)

    # Locate the cell for this specific (impl, test) pair by identity
    for cell in matrix.cells:
        if (all_impls_list[cell.impl_index] is impl
                and all_test_sets_list[cell.test_index] is test_set):
            return cell

    # Fallback: match by index position
    target_impl_idx = all_impls_list.index(impl)
    target_test_idx = all_test_sets_list.index(test_set)
    for cell in matrix.cells:
        if cell.impl_index == target_impl_idx and cell.test_index == target_test_idx:
            return cell

    raise RuntimeError(
        f"Cell for impl[{impl.index}] x test[{test_set.index}] not found in matrix"
    )


# ---------------------------------------------------------------------------
# AC-required name aliases (F-R7-454)
# ---------------------------------------------------------------------------


def score_kxk_matrix(
    impls: Sequence[CandidateImpl],
    test_sets: Sequence[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    AC-required alias for triangulate_kxk_matrix.

    Raises:
        ValueError: If either impls or test_sets is empty.
    """
    return triangulate_kxk_matrix(impls, test_sets, workspace=workspace)


def spawn_candidate_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateTestSet]:
    """Generate K candidate test sets (CodeT ICLR 2023 pattern).

    AC-required alias for spawn_k_tests.

    Raises:
        ValueError: If K < 1.
    """
    return spawn_k_tests(feature_id, acceptance_criteria, K=K, workspace=workspace)


def spawn_candidate_implementations(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 2,
    workspace: str | Path | None = None,
) -> list[CandidateImpl]:
    """Generate K candidate implementations (CodeT ICLR 2023 pattern).

    AC-required alias for spawn_k_impls.

    Raises:
        ValueError: If K < 1.
    """
    return spawn_k_impls(feature_id, acceptance_criteria, K=K, workspace=workspace)
