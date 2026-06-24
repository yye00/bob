"""CodeT mutual-agreement triangulation — KxK code-test matrix.

Implements the CodeT pattern (ICLR 2023) combined with TestGen-LLM's
Build/Pass/Coverage triple filter.

Primary entry points:

    spawn_k_candidates(feature_id, acceptance_criteria, K, workspace)
        → (impls, test_sets)

    score_kxk_matrix(impls, test_sets, workspace)
        → ScoredMatrix

Source: Agent 4 Section 9 (CodeT, ICLR 2023; TestGen-LLM).
"""

from __future__ import annotations

from pathlib import Path

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
    "build_kxk_matrix",
    "score_kxk_matrix",
    "score_mutual_agreement",
    "spawn_candidate_impls",
    "spawn_candidate_tests",
    "spawn_k_candidates",
    # Re-exported types
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


def spawn_k_candidates(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> tuple[list[CandidateImpl], list[CandidateTestSet]]:
    """Spawn K candidate implementations and K candidate test sets.

    Combines spawn_k_impls and spawn_k_tests into a single convenience call,
    producing the inputs needed by score_kxk_matrix.

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


def spawn_candidate_impls(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateImpl]:
    """Spawn K candidate implementations (alias for spawn_k_impls).

    AC alias: bob3.codet_mutual_agreement.spawn_candidate_impls.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings that guide generation.
        K: Number of candidates. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        List of K CandidateImpl instances.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")
    return spawn_k_impls(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )


def spawn_candidate_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateTestSet]:
    """Spawn K candidate test sets (alias for spawn_k_tests).

    AC alias: bob3.codet_mutual_agreement.spawn_candidate_tests.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings that guide generation.
        K: Number of candidates. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        List of K CandidateTestSet instances.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")
    return spawn_k_tests(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )


def score_kxk_matrix(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    For each (impl_i, test_j) cell:
        score = passing_tests * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail test set j, measuring the test set's discriminative power.

    The winner is the cell with the highest mutual-agreement score.
    Combined with TestGen-LLM's Build/Pass/Coverage triple filter, this is
    the cheapest known guard against AI-judge sycophancy.

    Args:
        impls: Candidate implementations from spawn_k_candidates or spawn_k_impls.
        test_sets: Candidate test sets from spawn_k_candidates or spawn_k_tests.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix with all cells scored and winner identified.

    Raises:
        ValueError: If either list is empty.
    """
    if not impls:
        raise ValueError("impls must not be empty")
    if not test_sets:
        raise ValueError("test_sets must not be empty")

    return score_matrix(impls, test_sets, workspace=workspace)


def build_kxk_matrix(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Build and score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    Alias for score_kxk_matrix — satisfies AC: Function defined:
    bob3.codet_mutual_agreement.build_kxk_matrix.

    Args:
        impls: Candidate implementations from spawn_k_candidates or spawn_k_impls.
        test_sets: Candidate test sets from spawn_k_candidates or spawn_k_tests.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix with all cells scored and winner identified.

    Raises:
        ValueError: If either list is empty.
    """
    return score_kxk_matrix(impls, test_sets, workspace=workspace)


def score_mutual_agreement(
    impl: CandidateImpl,
    test_set: CandidateTestSet,
    all_impls: list[CandidateImpl],
    all_test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> MatrixCell:
    """Compute mutual-agreement score for a single (impl, test) cell (CodeT, ICLR 2023).

    Satisfies AC: Function defined: bob3.codet_mutual_agreement.score_mutual_agreement.
    Delegates to bob3.codet_triangulation.score_mutual_agreement.

    Args:
        impl: The candidate implementation to score.
        test_set: The candidate test set to score against.
        all_impls: All candidate implementations for cross-impl unique_fail_count.
        all_test_sets: All candidate test sets for context.
        workspace: Project root directory (defaults to cwd).

    Returns:
        MatrixCell with the score for this (impl, test) pair.

    Raises:
        ValueError: If all_impls is empty.
    """
    from bob3.codet_triangulation import score_mutual_agreement as _score  # noqa: PLC0415
    return _score(impl, test_set, all_impls, all_test_sets, workspace=workspace)

