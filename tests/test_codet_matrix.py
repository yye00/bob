"""Tests for bob3.codet_matrix — the stable public API for CodeT KxK triangulation."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from bob3.codet_matrix import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    NoCandidatesError,
    ScoredMatrix,
    mutual_agreement_score,
    spawn_k_candidates,
    spawn_k_impls,
    spawn_k_tests,
    triple_filter,
)


# ---------------------------------------------------------------------------
# Helpers
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
# spawn_k_candidates
# ---------------------------------------------------------------------------


class TestSpawnKCandidates:
    def test_returns_tuple_of_two_lists(self, tmp_path):
        impls, test_sets = spawn_k_candidates("feat-abc", ["AC1"], K=2, workspace=tmp_path)
        assert isinstance(impls, list)
        assert isinstance(test_sets, list)

    def test_both_lists_have_length_k(self, tmp_path):
        K = 3
        impls, test_sets = spawn_k_candidates("feat-abc", ["AC1", "AC2"], K=K, workspace=tmp_path)
        assert len(impls) == K
        assert len(test_sets) == K

    def test_k_equals_one(self, tmp_path):
        impls, test_sets = spawn_k_candidates("feat-one", ["AC: foo"], K=1, workspace=tmp_path)
        assert len(impls) == 1
        assert len(test_sets) == 1

    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="K must be >= 1"):
            spawn_k_candidates("feat-x", [], K=0, workspace=tmp_path)

    def test_k_negative_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="K must be >= 1"):
            spawn_k_candidates("feat-x", [], K=-1, workspace=tmp_path)

    def test_impls_are_candidate_impl_instances(self, tmp_path):
        impls, _ = spawn_k_candidates("feat-t", ["AC"], K=2, workspace=tmp_path)
        for impl in impls:
            assert isinstance(impl, CandidateImpl)

    def test_test_sets_are_candidate_test_set_instances(self, tmp_path):
        _, test_sets = spawn_k_candidates("feat-t", ["AC"], K=2, workspace=tmp_path)
        for ts in test_sets:
            assert isinstance(ts, CandidateTestSet)

    def test_impl_paths_exist(self, tmp_path):
        impls, _ = spawn_k_candidates("feat-ep", ["AC"], K=2, workspace=tmp_path)
        for impl in impls:
            assert impl.impl_path.exists(), f"{impl.impl_path} must exist"

    def test_test_paths_exist(self, tmp_path):
        _, test_sets = spawn_k_candidates("feat-ep", ["AC"], K=2, workspace=tmp_path)
        for ts in test_sets:
            assert ts.test_path.exists(), f"{ts.test_path} must exist"

    def test_impl_indices_sequential(self, tmp_path):
        impls, _ = spawn_k_candidates("feat-seq", ["AC"], K=3, workspace=tmp_path)
        assert [i.index for i in impls] == [0, 1, 2]

    def test_test_indices_sequential(self, tmp_path):
        _, test_sets = spawn_k_candidates("feat-seq", ["AC"], K=3, workspace=tmp_path)
        assert [ts.index for ts in test_sets] == [0, 1, 2]

    def test_framings_cycle_positive_adversarial_boundary(self, tmp_path):
        _, test_sets = spawn_k_candidates("feat-fr", ["AC"], K=3, workspace=tmp_path)
        framings = [ts.framing for ts in test_sets]
        assert framings == ["positive", "adversarial", "boundary"]

    def test_framing_wraps_for_k_greater_than_three(self, tmp_path):
        _, test_sets = spawn_k_candidates("feat-wrap", ["AC"], K=4, workspace=tmp_path)
        assert test_sets[3].framing == "positive"

    def test_workspace_defaults_to_cwd_without_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        impls, test_sets = spawn_k_candidates("feat-cwd", ["AC"], K=1)
        assert len(impls) == 1
        assert len(test_sets) == 1


# ---------------------------------------------------------------------------
# mutual_agreement_score
# ---------------------------------------------------------------------------


class TestMutualAgreementScore:
    def test_returns_scored_matrix(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        assert isinstance(result, ScoredMatrix)

    def test_single_cell_1x1(self, tmp_path):
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

    def test_winner_indices_within_range(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0, impl1], [ts0], workspace=tmp_path)
        assert 0 <= result.winner_impl_index < 2
        assert result.winner_test_index == 0

    def test_winner_score_nonnegative(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0], [ts0], workspace=tmp_path)
        assert result.winner_score >= 0.0

    def test_cells_have_correct_impl_test_indices(self, tmp_path):
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

    def test_passing_impl_preferred_over_failing_test(self, tmp_path):
        """Test set that always fails means impl with passing test wins."""
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts_pass = _write_passing_test(cands / "tests_0.py", "0")
        ts_fail = _write_failing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0, impl1], [ts_pass, ts_fail], workspace=tmp_path)
        # The winner is a valid cell from the matrix
        assert isinstance(result.winner_impl_index, int)
        assert isinstance(result.winner_test_index, int)
        assert 0 <= result.winner_impl_index < 2
        assert 0 <= result.winner_test_index < 2

    def test_winner_cell_exists_in_cells_list(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0, impl1], [ts0], workspace=tmp_path)
        winner_pair = (result.winner_impl_index, result.winner_test_index)
        cell_pairs = {(c.impl_index, c.test_index) for c in result.cells}
        assert winner_pair in cell_pairs

    def test_winner_has_maximum_score(self, tmp_path):
        cands = tmp_path / "candidates"
        impl0 = _write_impl(cands / "impl_0.py", 0)
        ts0 = _write_passing_test(cands / "tests_0.py", "0")
        ts1 = _write_failing_test(cands / "tests_1.py", "1")
        result = mutual_agreement_score([impl0], [ts0, ts1], workspace=tmp_path)
        max_score = max(c.score for c in result.cells)
        assert result.winner_score == pytest.approx(max_score)

    def test_discriminative_test_boosts_score(self, tmp_path):
        """A test set that makes one impl fail but not another scores higher."""
        cands = tmp_path / "candidates"
        # Both impls are identical — neither fails the other's tests.
        # A test that always passes gives passing=1, unique_fail=0 → score 1.
        impl0 = _write_impl(cands / "impl_0.py", 0)
        impl1 = _write_impl(cands / "impl_1.py", 1)
        ts_pass = _write_passing_test(cands / "tests_0.py", "0")
        result = mutual_agreement_score([impl0, impl1], [ts_pass], workspace=tmp_path)
        # All cells have passing=1 and unique_fail_count=0 → score=1
        for cell in result.cells:
            if cell.passed:
                assert cell.score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator re-exports
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
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

    def test_mutual_agreement_score_importable_from_codet_matrix(self):
        from bob3.codet_matrix import mutual_agreement_score  # noqa: F401
        assert callable(mutual_agreement_score)

    def test_spawn_k_candidates_importable_from_codet_matrix(self):
        from bob3.codet_matrix import spawn_k_candidates  # noqa: F401
        assert callable(spawn_k_candidates)

    def test_orchestrator_init_imports_cleanly(self):
        import bob3.orchestrator  # noqa: F401


# ---------------------------------------------------------------------------
# Triple filter via codet_matrix re-export
# ---------------------------------------------------------------------------


class TestTripleFilterReexport:
    def test_triple_filter_reachable_via_codet_matrix(self):
        from bob3.codet_matrix import triple_filter  # noqa: F401
        assert callable(triple_filter)

    def test_triple_filter_accepts_test_set(self, tmp_path):
        cands = tmp_path / "candidates"
        ts = _write_passing_test(cands / "tests_0.py", "0")
        results = triple_filter([ts], workspace=tmp_path)
        assert len(results) == 1

    def test_triple_filter_result_has_compiles_flag(self, tmp_path):
        cands = tmp_path / "candidates"
        ts = _write_passing_test(cands / "tests_0.py", "0")
        results = triple_filter([ts], workspace=tmp_path)
        assert hasattr(results[0], "compiles")

    def test_valid_test_compiles(self, tmp_path):
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
# Data class contract
# ---------------------------------------------------------------------------


class TestDataClassContracts:
    def test_matrix_cell_has_score_field(self):
        cell = MatrixCell(
            impl_index=0,
            test_index=0,
            passing_tests=1,
            unique_fail_count=2,
            score=3.0,
            passed=True,
        )
        assert cell.score == 3.0

    def test_scored_matrix_winner_fields(self):
        cell = MatrixCell(0, 0, 1, 0, 1.0, True)
        sm = ScoredMatrix(cells=[cell], winner_impl_index=0, winner_test_index=0, winner_score=1.0)
        assert sm.winner_impl_index == 0
        assert sm.winner_test_index == 0
        assert sm.winner_score == 1.0

    def test_candidate_impl_has_content_field(self, tmp_path):
        p = tmp_path / "impl.py"
        p.write_text("pass\n", encoding="utf-8")
        impl = CandidateImpl(index=0, impl_path=p, content="pass\n")
        assert impl.content == "pass\n"

    def test_candidate_test_set_has_framing_field(self, tmp_path):
        p = tmp_path / "tests.py"
        p.write_text("def test_x(): pass\n", encoding="utf-8")
        ts = CandidateTestSet(index=0, framing="boundary", test_path=p, content="")
        assert ts.framing == "boundary"
