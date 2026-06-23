"""Boundary-case tests for CodeT KxK mutual-agreement triangulation.

AC: empty, zero, or minimum input returns a well-defined result rather than
raising (boundary case).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.codet_triangulation import generate_kxk_matrix, mutual_agreement_scorer
from bob3.orchestrator.codet_triangulation import spawn_k_impls, spawn_k_tests


class TestGenerateKxKMatrixBoundary:
    def test_k_equals_one_returns_single_cell(self, tmp_path):
        """Minimum K=1 produces a 1x1 matrix — well-defined, not an error."""
        impls = spawn_k_impls("boundary-k1-impl", ["AC1"], K=1, workspace=tmp_path)
        test_sets = spawn_k_tests("boundary-k1-test", ["AC1"], K=1, workspace=tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == 1
        assert result.winner_impl_index == 0
        assert result.winner_test_index == 0

    def test_empty_acceptance_criteria_does_not_raise(self, tmp_path):
        """Empty ACs: candidates generated from empty list — should not crash."""
        impls = spawn_k_impls("boundary-empty-ac", [], K=1, workspace=tmp_path)
        test_sets = spawn_k_tests("boundary-empty-ac", [], K=1, workspace=tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert result is not None
        assert len(result.cells) == 1

    def test_k_equals_one_winner_score_is_non_negative(self, tmp_path):
        """A 1x1 matrix always has a non-negative winner score."""
        impls = spawn_k_impls("boundary-score", ["AC1"], K=1, workspace=tmp_path)
        test_sets = spawn_k_tests("boundary-score", ["AC1"], K=1, workspace=tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert result.winner_score >= 0.0

    def test_single_candidate_symmetric_matrix(self, tmp_path):
        """1x1 matrix: winner indices are always (0, 0)."""
        impls = spawn_k_impls("boundary-sym", ["AC1"], K=1, workspace=tmp_path)
        test_sets = spawn_k_tests("boundary-sym", ["AC1"], K=1, workspace=tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert result.winner_impl_index == 0
        assert result.winner_test_index == 0


class TestMutualAgreementScorerBoundary:
    def test_single_impl_single_test_returns_cell(self, tmp_path):
        """Minimum boundary: 1 impl, 1 test — scorer must return a cell."""
        impls = spawn_k_impls("boundary-mas-k1", ["AC1"], K=1, workspace=tmp_path)
        test_sets = spawn_k_tests("boundary-mas-k1", ["AC1"], K=1, workspace=tmp_path)
        cell = mutual_agreement_scorer(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert cell is not None
        assert cell.score >= 0.0

    def test_empty_test_sets_in_scorer_falls_back(self, tmp_path):
        """When all_test_sets is empty, scorer uses the provided test_set alone."""
        impls = spawn_k_impls("boundary-mas-empty-ts", ["AC1"], K=1, workspace=tmp_path)
        test_sets = spawn_k_tests("boundary-mas-empty-ts", ["AC1"], K=1, workspace=tmp_path)
        cell = mutual_agreement_scorer(
            impls[0], test_sets[0], impls, [], workspace=tmp_path
        )
        assert cell is not None
        assert cell.score >= 0.0
