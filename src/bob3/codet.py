"""CodeT mutual-agreement triangulation — canonical entry point (F-R7-454).

Implements the CodeT pattern (ICLR 2023) combined with TestGen-LLM's
Build/Pass/Coverage triple filter.

The KxK code-test matrix pattern:
  1. spawn_candidate_tests: Generate K candidate test sets (positive, adversarial, boundary)
  2. spawn_candidate_impls: Generate K candidate implementations
  3. score_kxk_matrix: Score each (code, test) cell by mutual agreement —
     score = passing_tests * (unique_fail_count + 1)

The winner is the (impl, test) pair with the highest mutual-agreement score.
This removes the failure mode where a single bad test rubber-stamps a single
bad implementation, and is the cheapest known guard against AI-judge sycophancy.

Source: Agent 4 Section 9 (CodeT, ICLR 2023; TestGen-LLM).
"""

from __future__ import annotations

from pathlib import Path

from bob3.codet_matrix import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    NoCandidatesError,
    ScoredMatrix,
    TripleFilterResult,
    mutual_agreement_score,
    mutual_agreement_triangulation,
    score_kxk_matrix as _score_kxk_matrix,
    spawn_candidate_impls as _spawn_candidate_impls,
    spawn_candidate_tests as _spawn_candidate_tests,
    spawn_k_candidates,
)

__all__ = [
    "score_kxk_matrix",
    "spawn_candidate_tests",
    "spawn_candidate_impls",
    # Re-exported types
    "CandidateImpl",
    "CandidateTestSet",
    "MatrixCell",
    "NoCandidatesError",
    "ScoredMatrix",
    "TripleFilterResult",
    "mutual_agreement_score",
    "mutual_agreement_triangulation",
    "spawn_k_candidates",
]


def score_kxk_matrix(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Score a KxK code-test matrix by mutual agreement (CodeT, ICLR 2023).

    For each (impl_i, test_j) cell:
        score = passing_tests * (unique_fail_count + 1)

    where ``unique_fail_count`` is the number of OTHER implementations that
    fail test set j — measuring the test set's discriminative power.

    The winner is the cell with the highest mutual-agreement score.

    Args:
        impls: Candidate implementations from spawn_candidate_impls.
        test_sets: Candidate test sets from spawn_candidate_tests.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix with all cells scored and winner identified.

    Raises:
        ValueError: If either impls or test_sets is empty.
    """
    return _score_kxk_matrix(impls, test_sets, workspace=workspace)


def spawn_candidate_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> list[CandidateTestSet]:
    """Generate K candidate test sets for CodeT triangulation.

    Framings cycle through: positive, adversarial, boundary.
    Each test set is written to runs/<feature_id>/candidates/tests_<i>.py.

    Args:
        feature_id: The feature being tested.
        acceptance_criteria: List of AC strings to build tests from.
        K: Number of candidate test sets to produce. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        List of CandidateTestSet objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    return _spawn_candidate_tests(
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
    """Generate K candidate implementations for CodeT triangulation.

    Each implementation is written to runs/<feature_id>/candidates/impl_<i>.py.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings guiding candidate generation.
        K: Number of candidate implementations to produce. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        List of CandidateImpl objects, length K.

    Raises:
        ValueError: If K < 1.
    """
    return _spawn_candidate_impls(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
