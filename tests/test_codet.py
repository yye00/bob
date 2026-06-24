"""Tests for bob.codet — CodeT KxK mutual-agreement triangulation entry point."""

from __future__ import annotations

import pytest

from bob.codet import (
    CandidateImpl,
    CandidateTestSet,
    ScoredMatrix,
    score_kxk_matrix,
    spawn_candidate_impls,
    spawn_candidate_tests,
)


class TestSpawnCandidateTests:
    def test_returns_k_test_sets(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-1", ["AC1"], K=3, workspace=tmp_path)
        assert len(result) == 3

    def test_each_element_is_candidate_test_set(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-2", ["AC1"], K=2, workspace=tmp_path)
        for item in result:
            assert isinstance(item, CandidateTestSet)

    def test_k_equals_one_returns_one(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-k1", ["AC1"], K=1, workspace=tmp_path)
        assert len(result) == 1

    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            spawn_candidate_tests("feat-tc-k0", ["AC1"], K=0, workspace=tmp_path)

    def test_indices_are_sequential(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-idx", ["AC1"], K=3, workspace=tmp_path)
        assert [ts.index for ts in result] == [0, 1, 2]

    def test_test_files_are_written(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-files", ["AC1"], K=2, workspace=tmp_path)
        for ts in result:
            assert ts.test_path.exists()

    def test_content_is_non_empty(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-content", ["AC1"], K=1, workspace=tmp_path)
        assert result[0].content.strip()

    def test_empty_acs_does_not_raise(self, tmp_path):
        result = spawn_candidate_tests("feat-tc-empty-ac", [], K=1, workspace=tmp_path)
        assert len(result) == 1


class TestSpawnCandidateImpls:
    def test_returns_k_impls(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-1", ["AC1"], K=3, workspace=tmp_path)
        assert len(result) == 3

    def test_each_element_is_candidate_impl(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-2", ["AC1"], K=2, workspace=tmp_path)
        for item in result:
            assert isinstance(item, CandidateImpl)

    def test_k_equals_one_returns_one(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-k1", ["AC1"], K=1, workspace=tmp_path)
        assert len(result) == 1

    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            spawn_candidate_impls("feat-ci-k0", ["AC1"], K=0, workspace=tmp_path)

    def test_indices_are_sequential(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-idx", ["AC1"], K=3, workspace=tmp_path)
        assert [impl.index for impl in result] == [0, 1, 2]

    def test_impl_files_are_written(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-files", ["AC1"], K=2, workspace=tmp_path)
        for impl in result:
            assert impl.impl_path.exists()

    def test_content_is_non_empty(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-content", ["AC1"], K=1, workspace=tmp_path)
        assert result[0].content.strip()

    def test_empty_acs_does_not_raise(self, tmp_path):
        result = spawn_candidate_impls("feat-ci-empty-ac", [], K=1, workspace=tmp_path)
        assert len(result) == 1


class TestScoreKxKMatrix:
    def test_returns_scored_matrix(self, tmp_path):
        impls = spawn_candidate_impls("feat-km-1", ["AC1"], K=2, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-1", ["AC1"], K=2, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_kxk_cells_count(self, tmp_path):
        K = 2
        impls = spawn_candidate_impls("feat-km-cells", ["AC1"], K=K, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-cells", ["AC1"], K=K, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        assert len(result.cells) == K * K

    def test_winner_impl_index_in_range(self, tmp_path):
        K = 2
        impls = spawn_candidate_impls("feat-km-winner-i", ["AC1"], K=K, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-winner-i", ["AC1"], K=K, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        assert 0 <= result.winner_impl_index < K

    def test_winner_test_index_in_range(self, tmp_path):
        K = 2
        impls = spawn_candidate_impls("feat-km-winner-t", ["AC1"], K=K, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-winner-t", ["AC1"], K=K, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        assert 0 <= result.winner_test_index < K

    def test_winner_score_non_negative(self, tmp_path):
        impls = spawn_candidate_impls("feat-km-score", ["AC1"], K=2, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-score", ["AC1"], K=2, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        assert result.winner_score >= 0.0

    def test_empty_impls_raises_value_error(self, tmp_path):
        tests = spawn_candidate_tests("feat-km-ei", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError):
            score_kxk_matrix([], tests, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        impls = spawn_candidate_impls("feat-km-et", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError):
            score_kxk_matrix(impls, [], workspace=tmp_path)

    def test_k_equals_one_single_cell(self, tmp_path):
        impls = spawn_candidate_impls("feat-km-k1", ["AC1"], K=1, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-k1", ["AC1"], K=1, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        assert len(result.cells) == 1
        assert result.winner_impl_index == 0
        assert result.winner_test_index == 0

    def test_cells_have_required_fields(self, tmp_path):
        impls = spawn_candidate_impls("feat-km-fields", ["AC1"], K=2, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-fields", ["AC1"], K=2, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        for cell in result.cells:
            assert hasattr(cell, "impl_index")
            assert hasattr(cell, "test_index")
            assert hasattr(cell, "score")
            assert cell.score >= 0.0

    def test_winner_is_highest_scoring_cell(self, tmp_path):
        impls = spawn_candidate_impls("feat-km-best", ["AC1"], K=2, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-km-best", ["AC1"], K=2, workspace=tmp_path)
        result = score_kxk_matrix(impls, tests, workspace=tmp_path)
        max_score = max(c.score for c in result.cells)
        assert result.winner_score == pytest.approx(max_score)


class TestOrchestratorIntegration:
    def test_codet_importable_from_orchestrator(self):
        from bob import orchestrator
        assert hasattr(orchestrator, "score_kxk_matrix")
        assert hasattr(orchestrator, "spawn_candidate_tests")
        assert hasattr(orchestrator, "spawn_candidate_impls")

    def test_orchestrator_score_kxk_matrix_callable(self, tmp_path):
        from bob.orchestrator import score_kxk_matrix as orch_score
        impls = spawn_candidate_impls("feat-orch-score", ["AC1"], K=1, workspace=tmp_path)
        tests = spawn_candidate_tests("feat-orch-score", ["AC1"], K=1, workspace=tmp_path)
        result = orch_score(impls, tests, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)
