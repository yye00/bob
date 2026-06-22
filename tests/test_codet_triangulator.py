"""Tests for bob3.codet_triangulator module.

Verifies:
- triangulate_kxk_matrix function exists and returns a ScoredMatrix
- score_mutual_agreement function exists and returns a MatrixCell
- Both functions reject invalid inputs with ValueError
- Integration: functions are importable from bob3.codet_triangulator
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob3.codet_triangulator import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    ScoredMatrix,
    score_mutual_agreement,
    triangulate_kxk_matrix,
)
from bob3.orchestrator.codet_triangulation import spawn_k_impls, spawn_k_tests


def _make_candidates(feature_id: str, k: int, workspace: Path):
    """Helper: spawn k impls and k test sets into a temp workspace."""
    impls = spawn_k_impls(feature_id, ["AC1"], K=k, workspace=workspace)
    test_sets = spawn_k_tests(feature_id, ["AC1"], K=k, workspace=workspace)
    return impls, test_sets


class TestTriangulateKxKMatrix:
    def test_returns_scored_matrix(self, tmp_path):
        impls, test_sets = _make_candidates("triangulator-1", 2, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_matrix_has_kxk_cells(self, tmp_path):
        k = 2
        impls, test_sets = _make_candidates("triangulator-2", k, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == k * k

    def test_winner_indices_are_valid(self, tmp_path):
        impls, test_sets = _make_candidates("triangulator-3", 2, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert result.winner_impl_index >= 0
        assert result.winner_test_index >= 0
        assert result.winner_impl_index < len(impls)
        assert result.winner_test_index < len(test_sets)

    def test_winner_score_equals_max_cell_score(self, tmp_path):
        impls, test_sets = _make_candidates("triangulator-4", 2, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        max_score = max(c.score for c in result.cells)
        assert result.winner_score == pytest.approx(max_score)

    def test_k_equals_one_produces_single_cell(self, tmp_path):
        impls, test_sets = _make_candidates("triangulator-k1", 1, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == 1
        assert result.winner_impl_index == 0
        assert result.winner_test_index == 0

    def test_empty_impls_raises_value_error(self, tmp_path):
        test_sets = spawn_k_tests("triangulator-err-impls", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError, match="impls"):
            triangulate_kxk_matrix([], test_sets, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        impls = spawn_k_impls("triangulator-err-tests", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError, match="test_sets"):
            triangulate_kxk_matrix(impls, [], workspace=tmp_path)

    def test_both_empty_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            triangulate_kxk_matrix([], [], workspace=tmp_path)

    def test_all_cells_have_non_negative_scores(self, tmp_path):
        impls, test_sets = _make_candidates("triangulator-scores", 2, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        for cell in result.cells:
            assert cell.score >= 0.0

    def test_cells_have_valid_impl_and_test_indices(self, tmp_path):
        k = 3
        impls, test_sets = _make_candidates("triangulator-indices", k, tmp_path)
        result = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        for cell in result.cells:
            assert 0 <= cell.impl_index < k
            assert 0 <= cell.test_index < k


class TestScoreMutualAgreement:
    def test_returns_matrix_cell(self, tmp_path):
        impls, test_sets = _make_candidates("scorer-1", 2, tmp_path)
        cell = score_mutual_agreement(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell, MatrixCell)

    def test_cell_score_is_non_negative(self, tmp_path):
        impls, test_sets = _make_candidates("scorer-2", 2, tmp_path)
        cell = score_mutual_agreement(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert cell.score >= 0.0

    def test_single_impl_single_test(self, tmp_path):
        impls, test_sets = _make_candidates("scorer-k1", 1, tmp_path)
        cell = score_mutual_agreement(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert cell is not None
        assert cell.score >= 0.0

    def test_empty_all_impls_raises_value_error(self, tmp_path):
        test_sets = spawn_k_tests("scorer-err-impls", ["AC1"], K=1, workspace=tmp_path)
        dummy_impl = CandidateImpl(
            index=0, impl_path=tmp_path / "impl.py", content=""
        )
        with pytest.raises(ValueError, match="all_impls"):
            score_mutual_agreement(
                dummy_impl, test_sets[0], [], test_sets, workspace=tmp_path
            )

    def test_empty_all_test_sets_falls_back_to_provided_test_set(self, tmp_path):
        """When all_test_sets is empty, scorer uses the provided test_set alone."""
        impls, test_sets = _make_candidates("scorer-empty-ts", 1, tmp_path)
        cell = score_mutual_agreement(
            impls[0], test_sets[0], impls, [], workspace=tmp_path
        )
        assert cell is not None
        assert cell.score >= 0.0

    def test_impl_not_in_all_impls_is_added_automatically(self, tmp_path):
        """Impl not in all_impls list should be added and scored without error."""
        impls, test_sets = _make_candidates("scorer-add-impl", 1, tmp_path)
        extra_impls = spawn_k_impls("scorer-add-extra", ["AC1"], K=1, workspace=tmp_path)
        # extra_impls[0] is NOT in impls — scorer should add it
        cell = score_mutual_agreement(
            extra_impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell, MatrixCell)

    def test_cell_passing_tests_is_non_negative_integer(self, tmp_path):
        impls, test_sets = _make_candidates("scorer-passing", 2, tmp_path)
        cell = score_mutual_agreement(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell.passing_tests, int)
        assert cell.passing_tests >= 0

    def test_cell_unique_fail_count_is_non_negative_integer(self, tmp_path):
        impls, test_sets = _make_candidates("scorer-fails", 2, tmp_path)
        cell = score_mutual_agreement(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell.unique_fail_count, int)
        assert cell.unique_fail_count >= 0


class TestIntegration:
    def test_triangulate_then_score_consistency(self, tmp_path):
        """Score from triangulate_kxk_matrix should match score_mutual_agreement for same cell."""
        impls, test_sets = _make_candidates("integration-consistency", 2, tmp_path)
        matrix = triangulate_kxk_matrix(impls, test_sets, workspace=tmp_path)

        # Pick the winner cell and re-score it
        winner_impl = impls[matrix.winner_impl_index]
        winner_test = test_sets[matrix.winner_test_index]
        cell = score_mutual_agreement(
            winner_impl, winner_test, impls, test_sets, workspace=tmp_path
        )

        assert cell.score == pytest.approx(matrix.winner_score)

    def test_orchestrator_codet_triangulation_reachable(self):
        """Integration AC: bob3.orchestrator.codet_triangulation is reachable."""
        from bob3.orchestrator import codet_triangulation
        assert codet_triangulation is not None
