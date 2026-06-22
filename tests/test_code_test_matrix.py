"""Tests for bob3.code_test_matrix — CodeT KxK mutual-agreement triangulation.

Acceptance criteria verified:
  - File exists: src/bob3/code_test_matrix.py
  - Function defined: bob3.code_test_matrix.mutual_agreement_score
  - Function defined: bob3.code_test_matrix.spawn_kxk_matrix
  - integration: bob3.orchestrator
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.code_test_matrix import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    NoCandidatesError,
    ScoredMatrix,
    TripleFilterResult,
    mutual_agreement_score,
    mutual_agreement_triangulation,
    score_kxk_matrix,
    spawn_k_candidates,
    spawn_k_impls,
    spawn_k_tests,
    spawn_kxk_matrix,
    triple_filter,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _write_passing_test(path: Path, name_suffix: str = "0") -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = f"def test_always_passes_{name_suffix}():\n    assert True\n"
    path.write_text(src, encoding="utf-8")
    return CandidateTestSet(
        index=int(name_suffix) if name_suffix.isdigit() else 0,
        framing="positive",
        test_path=path,
        content=src,
    )


def _write_failing_test(path: Path, name_suffix: str = "1") -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = f"def test_always_fails_{name_suffix}():\n    assert False, 'sentinel failure'\n"
    path.write_text(src, encoding="utf-8")
    return CandidateTestSet(
        index=int(name_suffix) if name_suffix.isdigit() else 1,
        framing="adversarial",
        test_path=path,
        content=src,
    )


def _write_impl(path: Path, idx: int = 0) -> CandidateImpl:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = f"class Impl{idx}:\n    pass\n"
    path.write_text(src, encoding="utf-8")
    return CandidateImpl(index=idx, impl_path=path, content=src)


# ---------------------------------------------------------------------------
# Module-level import verification
# ---------------------------------------------------------------------------


class TestModuleExists:
    """AC: File exists: src/bob3/code_test_matrix.py"""

    def test_module_importable(self):
        import bob3.code_test_matrix  # noqa: F401

    def test_mutual_agreement_score_callable(self):
        assert callable(mutual_agreement_score)

    def test_spawn_kxk_matrix_callable(self):
        assert callable(spawn_kxk_matrix)

    def test_spawn_kxk_matrix_defined_in_module(self):
        import bob3.code_test_matrix as m
        assert hasattr(m, "spawn_kxk_matrix")

    def test_mutual_agreement_score_defined_in_module(self):
        import bob3.code_test_matrix as m
        assert hasattr(m, "mutual_agreement_score")

    def test_module_all_contains_primary_functions(self):
        import bob3.code_test_matrix as m
        assert "mutual_agreement_score" in m.__all__
        assert "spawn_kxk_matrix" in m.__all__


# ---------------------------------------------------------------------------
# spawn_kxk_matrix
# ---------------------------------------------------------------------------


class TestSpawnKxKMatrix:
    """AC: Function defined: bob3.code_test_matrix.spawn_kxk_matrix"""

    def test_returns_two_element_tuple(self, tmp_path):
        result = spawn_kxk_matrix("feat-abc", ["AC1"], K=2, workspace=tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_list_of_impls(self, tmp_path):
        impls, _ = spawn_kxk_matrix("feat-abc", ["AC1"], K=2, workspace=tmp_path)
        assert isinstance(impls, list)
        for impl in impls:
            assert isinstance(impl, CandidateImpl)

    def test_second_element_is_list_of_test_sets(self, tmp_path):
        _, test_sets = spawn_kxk_matrix("feat-abc", ["AC1"], K=2, workspace=tmp_path)
        assert isinstance(test_sets, list)
        for ts in test_sets:
            assert isinstance(ts, CandidateTestSet)

    def test_both_lists_have_length_k(self, tmp_path):
        K = 3
        impls, test_sets = spawn_kxk_matrix("feat-abc", ["AC1", "AC2"], K=K, workspace=tmp_path)
        assert len(impls) == K
        assert len(test_sets) == K

    def test_k_equals_one(self, tmp_path):
        impls, test_sets = spawn_kxk_matrix("feat-one", ["AC: foo"], K=1, workspace=tmp_path)
        assert len(impls) == 1
        assert len(test_sets) == 1

    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="K must be >= 1"):
            spawn_kxk_matrix("feat-x", [], K=0, workspace=tmp_path)

    def test_k_negative_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="K must be >= 1"):
            spawn_kxk_matrix("feat-x", [], K=-1, workspace=tmp_path)

    def test_impl_paths_exist_after_spawn(self, tmp_path):
        impls, _ = spawn_kxk_matrix("feat-ep", ["AC"], K=2, workspace=tmp_path)
        for impl in impls:
            assert impl.impl_path.exists(), f"{impl.impl_path} must exist after spawn"

    def test_test_paths_exist_after_spawn(self, tmp_path):
        _, test_sets = spawn_kxk_matrix("feat-ep", ["AC"], K=2, workspace=tmp_path)
        for ts in test_sets:
            assert ts.test_path.exists(), f"{ts.test_path} must exist after spawn"

    def test_impl_indices_sequential(self, tmp_path):
        impls, _ = spawn_kxk_matrix("feat-seq", ["AC"], K=3, workspace=tmp_path)
        assert [i.index for i in impls] == [0, 1, 2]

    def test_test_indices_sequential(self, tmp_path):
        _, test_sets = spawn_kxk_matrix("feat-seq", ["AC"], K=3, workspace=tmp_path)
        assert [ts.index for ts in test_sets] == [0, 1, 2]

    def test_framings_cycle_positive_adversarial_boundary(self, tmp_path):
        _, test_sets = spawn_kxk_matrix("feat-fr", ["AC"], K=3, workspace=tmp_path)
        framings = [ts.framing for ts in test_sets]
        assert framings == ["positive", "adversarial", "boundary"]

    def test_framing_wraps_for_k_greater_than_three(self, tmp_path):
        _, test_sets = spawn_kxk_matrix("feat-wrap", ["AC"], K=4, workspace=tmp_path)
        assert test_sets[3].framing == "positive"

    def test_workspace_defaults_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        impls, test_sets = spawn_kxk_matrix("feat-cwd", ["AC"], K=1)
        assert len(impls) == 1
        assert len(test_sets) == 1

    def test_k_equals_five(self, tmp_path):
        impls, test_sets = spawn_kxk_matrix("feat-5", ["AC"], K=5, workspace=tmp_path)
        assert len(impls) == 5
        assert len(test_sets) == 5

    def test_accepts_empty_acceptance_criteria(self, tmp_path):
        impls, test_sets = spawn_kxk_matrix("feat-empty-ac", [], K=2, workspace=tmp_path)
        assert len(impls) == 2
        assert len(test_sets) == 2

    def test_candidate_content_is_string(self, tmp_path):
        impls, test_sets = spawn_kxk_matrix("feat-content", ["AC"], K=2, workspace=tmp_path)
        for impl in impls:
            assert isinstance(impl.content, str)
        for ts in test_sets:
            assert isinstance(ts.content, str)


# ---------------------------------------------------------------------------
# mutual_agreement_score
# ---------------------------------------------------------------------------


class TestMutualAgreementScore:
    """AC: Function defined: bob3.code_test_matrix.mutual_agreement_score"""

    def test_returns_scored_matrix(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_1x1_matrix_has_one_cell(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        assert len(result.cells) == 1

    def test_2x2_matrix_has_four_cells(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        ts1 = _write_passing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0, impl1], [ts0, ts1], workspace=tmp_path)
        assert len(result.cells) == 4

    def test_3x3_matrix_has_nine_cells(self, tmp_path):
        cands = tmp_path / "candidates"
        impls = [_write_impl(cands / f"impl_{i}.py", i) for i in range(3)]
        test_sets = [_write_passing_test(cands / f"tests_{i}.py", str(i)) for i in range(3)]
        result = mutual_agreement_score(impls, test_sets, workspace=tmp_path)
        assert len(result.cells) == 9

    def test_winner_impl_index_within_range(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0, impl1], [ts0], workspace=tmp_path)
        assert 0 <= result.winner_impl_index < 2

    def test_winner_test_index_within_range(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        ts1 = _write_passing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0], [ts0, ts1], workspace=tmp_path)
        assert 0 <= result.winner_test_index < 2

    def test_winner_score_nonnegative(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        assert result.winner_score >= 0.0

    def test_cells_contain_expected_index_pairs(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        ts1 = _write_passing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0], [ts0, ts1], workspace=tmp_path)
        index_pairs = {(c.impl_index, c.test_index) for c in result.cells}
        assert (0, 0) in index_pairs
        assert (0, 1) in index_pairs

    def test_score_formula_passing_times_unique_fail_plus_one(self, tmp_path):
        """score = passing_tests * (unique_fail_count + 1)."""
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        cell = result.cells[0]
        expected = float(cell.passing_tests * (cell.unique_fail_count + 1))
        assert cell.score == pytest.approx(expected)

    def test_empty_impls_raises_value_error(self, tmp_path):
        cands = tmp_path / "candidates"
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        with pytest.raises(ValueError, match="impls must not be empty"):
            mutual_agreement_score([], [ts0], workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        with pytest.raises(ValueError, match="test_sets must not be empty"):
            mutual_agreement_score([impl0], [], workspace=tmp_path)

    def test_winner_cell_exists_in_cells_list(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0, impl1], [ts0], workspace=tmp_path)
        winner_pair = (result.winner_impl_index, result.winner_test_index)
        cell_pairs = {(c.impl_index, c.test_index) for c in result.cells}
        assert winner_pair in cell_pairs

    def test_winner_score_equals_max_cell_score(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        ts1 = _write_failing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0], [ts0, ts1], workspace=tmp_path)
        max_score = max(c.score for c in result.cells)
        assert result.winner_score == pytest.approx(max_score)

    def test_cells_have_matrix_cell_type(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        for cell in result.cells:
            assert isinstance(cell, MatrixCell)

    def test_all_cells_have_nonnegative_score(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        ts1 = _write_failing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0, impl1], [ts0, ts1], workspace=tmp_path)
        for cell in result.cells:
            assert cell.score >= 0.0

    def test_passing_test_gives_nonzero_score_for_passing_impl(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        cell = result.cells[0]
        assert cell.passed is True
        assert cell.passing_tests >= 1
        assert cell.score > 0.0


# ---------------------------------------------------------------------------
# Integration: spawn_kxk_matrix + mutual_agreement_score pipeline
# ---------------------------------------------------------------------------


class TestSpawnAndScorePipeline:
    """End-to-end pipeline: spawn_kxk_matrix → mutual_agreement_score."""

    def test_pipeline_produces_valid_scored_matrix(self, tmp_path):
        impls, test_sets = spawn_kxk_matrix("feat-pipeline", ["AC1"], K=2, workspace=tmp_path)
        result = mutual_agreement_score(impls, test_sets, workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)
        assert len(result.cells) == 4  # 2x2

    def test_pipeline_winner_indices_valid(self, tmp_path):
        K = 3
        impls, test_sets = spawn_kxk_matrix("feat-winner", ["AC"], K=K, workspace=tmp_path)
        result = mutual_agreement_score(impls, test_sets, workspace=tmp_path)
        assert 0 <= result.winner_impl_index < K
        assert 0 <= result.winner_test_index < K

    def test_mutual_agreement_triangulation_end_to_end(self, tmp_path):
        result = mutual_agreement_triangulation(
            "feat-e2e", ["AC1", "AC2"], K=2, workspace=tmp_path
        )
        assert isinstance(result, ScoredMatrix)
        assert result.winner_score >= 0.0

    def test_score_kxk_matrix_alias_works(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = score_kxk_matrix([impl0], [ts0], workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_spawn_k_candidates_alias_works(self, tmp_path):
        impls, test_sets = spawn_k_candidates("feat-compat", ["AC"], K=2, workspace=tmp_path)
        assert len(impls) == 2
        assert len(test_sets) == 2


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    """AC: integration: bob3.orchestrator"""

    def test_orchestrator_importable(self):
        import bob3.orchestrator  # noqa: F401

    def test_codet_triangulation_importable_from_orchestrator(self):
        from bob3.orchestrator import codet_triangulation  # noqa: F401

    def test_spawn_k_tests_importable_from_orchestrator(self):
        from bob3.orchestrator.codet_triangulation import spawn_k_tests  # noqa: F401
        assert callable(spawn_k_tests)

    def test_spawn_k_impls_importable_from_orchestrator(self):
        from bob3.orchestrator.codet_triangulation import spawn_k_impls  # noqa: F401
        assert callable(spawn_k_impls)

    def test_score_matrix_importable_from_orchestrator(self):
        from bob3.orchestrator.codet_triangulation import score_matrix  # noqa: F401
        assert callable(score_matrix)

    def test_mutual_agreement_score_importable_from_code_test_matrix(self):
        from bob3.code_test_matrix import mutual_agreement_score  # noqa: F401
        assert callable(mutual_agreement_score)

    def test_spawn_kxk_matrix_importable_from_code_test_matrix(self):
        from bob3.code_test_matrix import spawn_kxk_matrix  # noqa: F401
        assert callable(spawn_kxk_matrix)

    def test_orchestrator_does_not_fail_on_import(self):
        import importlib
        import bob3.orchestrator as orch
        # Re-importing should not raise
        importlib.reload(orch)

    def test_code_test_matrix_delegates_to_orchestrator_codet_triangulation(self):
        from bob3.orchestrator.codet_triangulation import score_matrix as _score_matrix
        from bob3.code_test_matrix import score_matrix as cm_score_matrix
        assert cm_score_matrix is _score_matrix


# ---------------------------------------------------------------------------
# Triple filter re-export
# ---------------------------------------------------------------------------


class TestTripleFilterReexport:
    def test_triple_filter_reachable_via_code_test_matrix(self):
        from bob3.code_test_matrix import triple_filter  # noqa: F401
        assert callable(triple_filter)

    def test_triple_filter_accepts_test_set(self, tmp_path):
        cands = tmp_path / "candidates"
        ts = _write_passing_test(cands / "tests_0.py", "0")
        results = triple_filter([ts], workspace=tmp_path)
        assert len(results) == 1

    def test_triple_filter_result_is_triple_filter_result(self, tmp_path):
        cands = tmp_path / "candidates"
        ts = _write_passing_test(cands / "tests_0.py", "0")
        results = triple_filter([ts], workspace=tmp_path)
        assert isinstance(results[0], TripleFilterResult)

    def test_valid_syntax_test_compiles(self, tmp_path):
        cands = tmp_path / "candidates"
        ts = _write_passing_test(cands / "tests_0.py", "0")
        results = triple_filter([ts], workspace=tmp_path)
        assert results[0].compiles is True

    def test_syntax_error_test_does_not_compile(self, tmp_path):
        cands = tmp_path / "candidates"
        cands.mkdir(parents=True, exist_ok=True)
        bad_path = cands / "tests_bad.py"
        bad_path.write_text("def test_broken(\n    assert True\n", encoding="utf-8")
        ts_bad = CandidateTestSet(index=99, framing="positive", test_path=bad_path, content="")
        results = triple_filter([ts_bad], workspace=tmp_path)
        assert results[0].compiles is False
        assert results[0].accepted is False


# ---------------------------------------------------------------------------
# Data class contracts
# ---------------------------------------------------------------------------


class TestDataClassContracts:
    def test_matrix_cell_score_field(self):
        cell = MatrixCell(
            impl_index=0, test_index=0, passing_tests=1,
            unique_fail_count=2, score=3.0, passed=True,
        )
        assert cell.score == 3.0

    def test_matrix_cell_passed_field(self):
        cell = MatrixCell(
            impl_index=1, test_index=2, passing_tests=0,
            unique_fail_count=0, score=0.0, passed=False,
        )
        assert cell.passed is False

    def test_scored_matrix_has_winner_fields(self):
        cell = MatrixCell(0, 0, 1, 0, 1.0, True)
        sm = ScoredMatrix(cells=[cell], winner_impl_index=0, winner_test_index=0, winner_score=1.0)
        assert sm.winner_impl_index == 0
        assert sm.winner_test_index == 0
        assert sm.winner_score == 1.0

    def test_candidate_impl_has_content(self, tmp_path):
        p = tmp_path / "impl.py"
        p.write_text("pass\n", encoding="utf-8")
        impl = CandidateImpl(index=0, impl_path=p, content="pass\n")
        assert impl.content == "pass\n"

    def test_candidate_test_set_has_framing(self, tmp_path):
        p = tmp_path / "tests.py"
        p.write_text("def test_x(): pass\n", encoding="utf-8")
        ts = CandidateTestSet(index=0, framing="boundary", test_path=p, content="")
        assert ts.framing == "boundary"

    def test_no_candidates_error_is_value_error(self):
        assert issubclass(NoCandidatesError, ValueError)
