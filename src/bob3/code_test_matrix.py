"""CodeT mutual-agreement triangulation — KxK code-test matrix (stable public API).

Implements the KxK code-test matrix scoring strategy from CodeT (ICLR 2023)
combined with TestGen-LLM's Build/Pass/Coverage triple filter.

This module is the canonical importable entry point required by the feature AC
``bob3.code_test_matrix.*``.  Heavy lifting is in
``bob3.orchestrator.codet_triangulation``; this module re-exports everything and
adds the ``spawn_kxk_matrix`` convenience function required by the AC suite.

Public API::

    from bob3.code_test_matrix import (
        spawn_kxk_matrix,          # AC: Function defined: bob3.code_test_matrix.spawn_kxk_matrix
        mutual_agreement_score,    # AC: Function defined: bob3.code_test_matrix.mutual_agreement_score
    )

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
from bob3.codet_triangulation import (
    spawn_candidate_tests,
    spawn_candidate_impls,
)

__all__ = [
    # Primary AC-required entry points
    "mutual_agreement_score",
    "spawn_kxk_matrix",
    "spawn_candidate_tests",
    "spawn_candidate_impls",
    # Secondary convenience helpers
    "spawn_k_candidates",
    "mutual_agreement_triangulation",
    "score_kxk_matrix",
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


def spawn_kxk_matrix(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> tuple[list[CandidateImpl], list[CandidateTestSet]]:
    """Spawn K candidate implementations and K candidate test sets for the KxK matrix.

    This is the primary entry point for the CodeT triangulation pipeline
    (ICLR 2023).  It combines ``spawn_k_impls`` and ``spawn_k_tests`` into a
    single convenience call, producing the inputs needed by
    ``mutual_agreement_score``.

    Combined with TestGen-LLM's Build/Pass/Coverage triple filter (see
    ``triple_filter``), this is the cheapest known guard against AI-judge
    sycophancy that the recursive bob3 framework has documented.

    Args:
        feature_id: The feature being implemented.
        acceptance_criteria: List of AC strings that guide candidate generation.
        K: Number of candidates for each side of the matrix. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        A 2-tuple ``(impls, test_sets)`` where both lists have length K.
        Pass these directly to ``mutual_agreement_score`` to score the matrix.

    Raises:
        ValueError: If K < 1.

    Example::

        impls, test_sets = spawn_kxk_matrix("feat-abc", ["AC: foo", "AC: bar"], K=3)
        result = mutual_agreement_score(impls, test_sets)
        print(f"Winner: impl={result.winner_impl_index}, test={result.winner_test_index}")
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

    The winner is the cell with the highest score.  Ties are broken by lowest
    impl_index then test_index.

    Args:
        impls: Candidate implementations from ``spawn_kxk_matrix`` or ``spawn_k_impls``.
        test_sets: Candidate test sets from ``spawn_kxk_matrix`` or ``spawn_k_tests``.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix identifying the winning (impl, test) pair and all scores.

    Raises:
        ValueError: If either list is empty.

    Example::

        impls, test_sets = spawn_kxk_matrix("feat-abc", ["AC: foo"], K=3)
        result = mutual_agreement_score(impls, test_sets)
        winner_impl = impls[result.winner_impl_index]
        winner_tests = test_sets[result.winner_test_index]
    """
    if not impls:
        raise ValueError("impls must not be empty")
    if not test_sets:
        raise ValueError("test_sets must not be empty")

    return score_matrix(impls, test_sets, workspace=workspace)


def spawn_k_candidates(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> tuple[list[CandidateImpl], list[CandidateTestSet]]:
    """Alias for spawn_kxk_matrix — backward-compatible name.

    See ``spawn_kxk_matrix`` for full documentation.
    """
    return spawn_kxk_matrix(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )


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

    impls, test_sets = spawn_kxk_matrix(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )
    return mutual_agreement_score(impls, test_sets, workspace=workspace)


def score_kxk_matrix(
    impls: list[CandidateImpl],
    test_sets: list[CandidateTestSet],
    workspace: str | Path | None = None,
) -> ScoredMatrix:
    """Alias for mutual_agreement_score with an explicit KxK name.

    For each (impl_i, test_j) cell:
        score = passing_tests * (unique_fail_count + 1)

    Args:
        impls: Candidate implementations.
        test_sets: Candidate test sets.
        workspace: Project root directory (defaults to cwd).

    Returns:
        ScoredMatrix with all cells scored and winner identified.

    Raises:
        ValueError: If either list is empty.
    """
    return mutual_agreement_score(impls, test_sets, workspace=workspace)
