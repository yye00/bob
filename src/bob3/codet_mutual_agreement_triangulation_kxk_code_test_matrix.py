"""CodeT mutual-agreement triangulation — KxK code-test matrix.

Implements the CodeT pattern (ICLR 2023) combined with TestGen-LLM's
Build/Pass/Coverage triple filter.  Spawns K candidate implementations and K
candidate test sets, scores the resulting KxK matrix by mutual agreement, and
returns the winning (impl, test) pair.

Source: Agent 4 Section 9 (CodeT, ICLR 2023; TestGen-LLM).
"""

from __future__ import annotations

from pathlib import Path

from bob3.codet_matrix import (
    CandidateImpl,
    CandidateTestSet,
    ScoredMatrix,
    mutual_agreement_triangulation,
    spawn_k_candidates,
)

__all__ = ["codet_mutual_agreement_triangulation_kxk_code_test_matrix"]

_FRAMINGS = ["positive", "adversarial", "boundary"]


def codet_mutual_agreement_triangulation_kxk_code_test_matrix(
    feature_id: str,
    acceptance_criteria: list[str],
    K: int = 3,
    workspace: str | Path | None = None,
) -> dict:
    """Run CodeT KxK mutual-agreement triangulation and return scored results.

    Spawns K candidate implementations and K candidate test sets, scores the
    KxK matrix by mutual agreement (CodeT, ICLR 2023), and returns a dict
    summarising the winning cell and full matrix.

    The mutual-agreement score for cell (i, j) is:
        score = passing_tests * (unique_fail_count + 1)

    Combined with TestGen-LLM's Build/Pass/Coverage triple filter, this is
    the cheapest known guard against AI-judge sycophancy.

    Args:
        feature_id: Identifier for the feature being implemented.
        acceptance_criteria: List of AC strings guiding candidate generation.
        K: Number of candidates for each side of the matrix. Must be >= 1.
        workspace: Project root directory (defaults to cwd).

    Returns:
        dict with keys:
            feature_id: The feature identifier.
            k: The K value used.
            winner_impl_index: Index of the winning implementation.
            winner_test_index: Index of the winning test set.
            winner_score: Score of the winning cell.
            cells: List of dicts, each with impl_index, test_index, score.

    Raises:
        ValueError: If K < 1.
    """
    if K < 1:
        raise ValueError("K must be >= 1")

    scored: ScoredMatrix = mutual_agreement_triangulation(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        K=K,
        workspace=workspace,
    )

    cells = [
        {
            "impl_index": cell.impl_index,
            "test_index": cell.test_index,
            "score": float(cell.score),
            "passing_tests": cell.passing_tests,
            "unique_fail_count": cell.unique_fail_count,
            "passed": cell.passed,
        }
        for cell in scored.cells
    ]

    return {
        "feature_id": feature_id,
        "k": K,
        "winner_impl_index": scored.winner_impl_index,
        "winner_test_index": scored.winner_test_index,
        "winner_score": float(scored.winner_score),
        "cells": cells,
    }
