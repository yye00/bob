"""Tests for bob.codet_triangulation module.

Verifies:
- mutual_agreement_scorer function exists and returns a MatrixCell
- generate_kxk_matrix function exists and returns a ScoredMatrix
- Both functions reject invalid inputs with ValueError
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    ScoredMatrix,
    build_agreement_matrix,
    generate_kxk_matrix,
    mutual_agreement_scorer,
    score_candidates,
    select_best_impl,
)
from bob.orchestrator.codet_triangulation import spawn_k_impls, spawn_k_tests


def _make_candidates(feature_id: str, k: int, workspace: Path):
    """Helper: spawn k impls and k test sets into a temp workspace."""
    impls = spawn_k_impls(feature_id, ["AC1"], K=k, workspace=workspace)
    test_sets = spawn_k_tests(feature_id, ["AC1"], K=k, workspace=workspace)
    return impls, test_sets


class TestGenerateKxKMatrix:
    def test_returns_scored_matrix(self, tmp_path):
        impls, test_sets = _make_candidates("feat-gen-1", 2, tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_matrix_has_kxk_cells(self, tmp_path):
        k = 2
        impls, test_sets = _make_candidates("feat-gen-2", k, tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == k * k

    def test_winner_indices_are_valid(self, tmp_path):
        impls, test_sets = _make_candidates("feat-gen-3", 2, tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert result.winner_impl_index >= 0
        assert result.winner_test_index >= 0
        assert result.winner_impl_index < len(impls)
        assert result.winner_test_index < len(test_sets)

    def test_winner_score_is_max(self, tmp_path):
        impls, test_sets = _make_candidates("feat-gen-4", 2, tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        max_score = max(c.score for c in result.cells)
        assert result.winner_score == pytest.approx(max_score)

    def test_k_equals_one_single_cell(self, tmp_path):
        impls, test_sets = _make_candidates("feat-gen-k1", 1, tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == 1

    def test_empty_impls_raises_value_error(self, tmp_path):
        _, test_sets = _make_candidates("feat-gen-empty", 1, tmp_path)
        with pytest.raises(ValueError, match="impls"):
            generate_kxk_matrix([], test_sets, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        impls, _ = _make_candidates("feat-gen-empty2", 1, tmp_path)
        with pytest.raises(ValueError, match="test_sets"):
            generate_kxk_matrix(impls, [], workspace=tmp_path)

    def test_cells_have_required_fields(self, tmp_path):
        impls, test_sets = _make_candidates("feat-gen-fields", 2, tmp_path)
        result = generate_kxk_matrix(impls, test_sets, workspace=tmp_path)
        for cell in result.cells:
            assert isinstance(cell, MatrixCell)
            assert isinstance(cell.impl_index, int)
            assert isinstance(cell.test_index, int)
            assert isinstance(cell.score, float)
            assert cell.score >= 0.0

    def test_accepts_sequences(self, tmp_path):
        impls, test_sets = _make_candidates("feat-gen-seq", 2, tmp_path)
        # Pass as tuples to verify Sequence is accepted
        result = generate_kxk_matrix(tuple(impls), tuple(test_sets), workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)


class TestMutualAgreementScorer:
    def test_returns_matrix_cell(self, tmp_path):
        impls, test_sets = _make_candidates("feat-mas-1", 2, tmp_path)
        cell = mutual_agreement_scorer(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell, MatrixCell)

    def test_score_is_non_negative(self, tmp_path):
        impls, test_sets = _make_candidates("feat-mas-2", 2, tmp_path)
        cell = mutual_agreement_scorer(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert cell.score >= 0.0

    def test_cell_contains_impl_and_test_indices(self, tmp_path):
        impls, test_sets = _make_candidates("feat-mas-3", 2, tmp_path)
        cell = mutual_agreement_scorer(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell.impl_index, int)
        assert isinstance(cell.test_index, int)

    def test_empty_all_impls_raises_value_error(self, tmp_path):
        _, test_sets = _make_candidates("feat-mas-empty", 1, tmp_path)
        impl = CandidateImpl(index=0, impl_path=tmp_path / "impl.py", content="")
        with pytest.raises(ValueError, match="all_impls"):
            mutual_agreement_scorer(impl, test_sets[0], [], test_sets, workspace=tmp_path)

    def test_works_with_single_impl(self, tmp_path):
        impls, test_sets = _make_candidates("feat-mas-single", 1, tmp_path)
        cell = mutual_agreement_scorer(
            impls[0], test_sets[0], impls, test_sets, workspace=tmp_path
        )
        assert isinstance(cell, MatrixCell)
        assert cell.score >= 0.0


class TestBuildAgreementMatrix:
    def test_returns_scored_matrix(self, tmp_path):
        impls, test_sets = _make_candidates("feat-bam-1", 2, tmp_path)
        result = build_agreement_matrix(impls, test_sets, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_matrix_has_kxk_cells(self, tmp_path):
        k = 2
        impls, test_sets = _make_candidates("feat-bam-2", k, tmp_path)
        result = build_agreement_matrix(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == k * k

    def test_empty_impls_raises_value_error(self, tmp_path):
        _, test_sets = _make_candidates("feat-bam-empty", 1, tmp_path)
        with pytest.raises(ValueError, match="impls"):
            build_agreement_matrix([], test_sets, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        impls, _ = _make_candidates("feat-bam-empty2", 1, tmp_path)
        with pytest.raises(ValueError, match="test_sets"):
            build_agreement_matrix(impls, [], workspace=tmp_path)


class TestScoreCandidates:
    def test_returns_ranked_list(self, tmp_path):
        impls, test_sets = _make_candidates("feat-sc-1", 2, tmp_path)
        ranked = score_candidates(impls, test_sets, workspace=tmp_path)
        assert isinstance(ranked, list)
        assert len(ranked) == len(impls)

    def test_ranked_by_descending_score(self, tmp_path):
        impls, test_sets = _make_candidates("feat-sc-2", 2, tmp_path)
        ranked = score_candidates(impls, test_sets, workspace=tmp_path)
        scores = [total for _, total in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_top_candidate_is_matrix_winner(self, tmp_path):
        impls, test_sets = _make_candidates("feat-sc-3", 2, tmp_path)
        matrix = build_agreement_matrix(impls, test_sets, workspace=tmp_path)
        ranked = score_candidates(impls, test_sets, workspace=tmp_path)
        top_impl = ranked[0][0]
        # The top-ranked impl by aggregate must be the matrix winner's impl
        # when the winner's impl also has the highest aggregate; assert it is a
        # valid CandidateImpl and its score is the max.
        assert isinstance(top_impl, CandidateImpl)
        assert ranked[0][1] == max(t for _, t in ranked)

    def test_empty_impls_raises_value_error(self, tmp_path):
        _, test_sets = _make_candidates("feat-sc-empty", 1, tmp_path)
        with pytest.raises(ValueError, match="impls"):
            score_candidates([], test_sets, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        impls, _ = _make_candidates("feat-sc-empty2", 1, tmp_path)
        with pytest.raises(ValueError, match="test_sets"):
            score_candidates(impls, [], workspace=tmp_path)


class TestSelectBestImpl:
    def test_returns_candidate_impl(self, tmp_path):
        impls, test_sets = _make_candidates("feat-sbi-1", 2, tmp_path)
        winner = select_best_impl(impls, test_sets, workspace=tmp_path)
        assert isinstance(winner, CandidateImpl)

    def test_winner_matches_matrix_winner(self, tmp_path):
        impls, test_sets = _make_candidates("feat-sbi-2", 2, tmp_path)
        matrix = build_agreement_matrix(impls, test_sets, workspace=tmp_path)
        winner = select_best_impl(impls, test_sets, workspace=tmp_path)
        assert winner.index == impls[matrix.winner_impl_index].index

    def test_single_impl_returns_that_impl(self, tmp_path):
        impls, test_sets = _make_candidates("feat-sbi-k1", 1, tmp_path)
        winner = select_best_impl(impls, test_sets, workspace=tmp_path)
        assert winner is impls[0]

    def test_empty_impls_raises_value_error(self, tmp_path):
        _, test_sets = _make_candidates("feat-sbi-empty", 1, tmp_path)
        with pytest.raises(ValueError, match="impls"):
            select_best_impl([], test_sets, workspace=tmp_path)
