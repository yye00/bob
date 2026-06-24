"""Tests for bob.codet_mutual_agreement module.

Verifies that score_kxk_matrix and spawn_k_candidates are importable,
callable, and return well-structured results.
"""

from __future__ import annotations

import pytest

from bob.codet_mutual_agreement import (
    CandidateImpl,
    CandidateTestSet,
    ScoredMatrix,
    score_kxk_matrix,
    spawn_k_candidates,
)


class TestSpawnKCandidates:
    def test_returns_tuple_of_two_lists(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "feat-001", ["AC1"], K=1, workspace=tmp_path
        )
        assert isinstance(impls, list)
        assert isinstance(test_sets, list)

    def test_returns_k_impls_and_k_tests(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "feat-002", ["AC1", "AC2"], K=2, workspace=tmp_path
        )
        assert len(impls) == 2
        assert len(test_sets) == 2

    def test_k_equals_one_returns_single_candidates(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "feat-003", ["AC1"], K=1, workspace=tmp_path
        )
        assert len(impls) == 1
        assert len(test_sets) == 1

    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="K must be >= 1"):
            spawn_k_candidates("feat-004", ["AC1"], K=0, workspace=tmp_path)

    def test_k_negative_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="K must be >= 1"):
            spawn_k_candidates("feat-005", ["AC1"], K=-1, workspace=tmp_path)

    def test_empty_acceptance_criteria_does_not_raise(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "feat-006", [], K=1, workspace=tmp_path
        )
        assert len(impls) == 1
        assert len(test_sets) == 1

    def test_impls_are_candidate_impl_instances(self, tmp_path):
        impls, _ = spawn_k_candidates("feat-007", ["AC1"], K=1, workspace=tmp_path)
        for impl in impls:
            assert isinstance(impl, CandidateImpl)

    def test_test_sets_are_candidate_test_set_instances(self, tmp_path):
        _, test_sets = spawn_k_candidates("feat-008", ["AC1"], K=1, workspace=tmp_path)
        for ts in test_sets:
            assert isinstance(ts, CandidateTestSet)


class TestScoreKxKMatrix:
    def test_returns_scored_matrix(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-001", ["AC1"], K=1, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_k1_produces_single_cell(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-002", ["AC1"], K=1, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == 1

    def test_k2_produces_four_cells(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-003", ["AC1"], K=2, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == 4

    def test_winner_impl_index_is_valid(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-004", ["AC1"], K=2, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert 0 <= result.winner_impl_index < len(impls)

    def test_winner_test_index_is_valid(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-005", ["AC1"], K=2, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert 0 <= result.winner_test_index < len(test_sets)

    def test_winner_score_is_non_negative(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-006", ["AC1"], K=1, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert result.winner_score >= 0.0

    def test_winner_score_equals_max_cell_score(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-007", ["AC1"], K=2, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        max_score = max(c.score for c in result.cells)
        assert result.winner_score == pytest.approx(max_score)

    def test_empty_impls_raises_value_error(self, tmp_path):
        _, test_sets = spawn_k_candidates(
            "score-008", ["AC1"], K=1, workspace=tmp_path
        )
        with pytest.raises(ValueError, match="impls"):
            score_kxk_matrix([], test_sets, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        impls, _ = spawn_k_candidates(
            "score-009", ["AC1"], K=1, workspace=tmp_path
        )
        with pytest.raises(ValueError, match="test_sets"):
            score_kxk_matrix(impls, [], workspace=tmp_path)

    def test_cells_have_required_attributes(self, tmp_path):
        impls, test_sets = spawn_k_candidates(
            "score-010", ["AC1"], K=2, workspace=tmp_path
        )
        result = score_kxk_matrix(impls, test_sets, workspace=tmp_path)
        for cell in result.cells:
            assert hasattr(cell, "impl_index")
            assert hasattr(cell, "test_index")
            assert hasattr(cell, "score")
            assert hasattr(cell, "passing_tests")
            assert hasattr(cell, "unique_fail_count")
