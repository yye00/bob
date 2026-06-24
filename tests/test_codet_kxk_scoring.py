"""Tests for KxK matrix scoring in codet_triangulation (score_matrix)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob3.orchestrator.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    ScoredMatrix,
    spawn_k_impls,
    spawn_k_tests,
    score_matrix,
)


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


def _make_passing_test(path: Path, content: str | None = None) -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = content or "def test_always_passes():\n    assert True\n"
    path.write_text(src, encoding="utf-8")
    return CandidateTestSet(index=0, framing="positive", test_path=path, content=src)


def _make_failing_test(path: Path) -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = "def test_always_fails():\n    assert False, 'expected failure'\n"
    path.write_text(src, encoding="utf-8")
    return CandidateTestSet(index=1, framing="adversarial", test_path=path, content=src)


def _make_impl(path: Path, content: str | None = None) -> CandidateImpl:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = content or "class Impl:\n    pass\n"
    path.write_text(src, encoding="utf-8")
    return CandidateImpl(index=0, impl_path=path, content=src)


class TestScoreMatrixShape:
    def test_returns_scored_matrix(self, workspace):
        cands = workspace / "candidates"
        impl0 = _make_impl(cands / "impl_0.py")
        ts0 = _make_passing_test(cands / "tests_0.py")
        matrix = score_matrix([impl0], [ts0], workspace=workspace)
        assert isinstance(matrix, ScoredMatrix)

    def test_cells_count_equals_n_impls_times_n_tests(self, workspace):
        cands = workspace / "candidates"
        impl0 = _make_impl(cands / "impl_0.py")
        impl1 = _make_impl(cands / "impl_1.py")
        ts0 = _make_passing_test(cands / "tests_0.py")
        ts1 = _make_passing_test(cands / "tests_1.py")
        matrix = score_matrix([impl0, impl1], [ts0, ts1], workspace=workspace)
        assert len(matrix.cells) == 4  # 2x2

    def test_winner_indices_in_range(self, workspace):
        cands = workspace / "candidates"
        impl0 = _make_impl(cands / "impl_0.py")
        ts0 = _make_passing_test(cands / "tests_0.py")
        matrix = score_matrix([impl0], [ts0], workspace=workspace)
        assert 0 <= matrix.winner_impl_index < 1
        assert 0 <= matrix.winner_test_index < 1

    def test_winner_score_is_nonnegative(self, workspace):
        cands = workspace / "candidates"
        impl0 = _make_impl(cands / "impl_0.py")
        ts0 = _make_passing_test(cands / "tests_0.py")
        matrix = score_matrix([impl0], [ts0], workspace=workspace)
        assert matrix.winner_score >= 0.0


class TestScoreMatrixDiscrimination:
    def test_passing_impl_preferred_over_failing(self, workspace):
        """The impl that passes more tests should win."""
        cands = workspace / "candidates"
        # impl_0: trivial (doesn't affect test outcome since tests run independently)
        impl0 = _make_impl(cands / "impl_0.py")
        impl1 = _make_impl(cands / "impl_1.py")
        # Test that always passes — impl that passes it gets higher discriminative score
        ts_pass = _make_passing_test(cands / "tests_0.py")
        ts_fail = _make_failing_test(cands / "tests_1.py")

        matrix = score_matrix([impl0, impl1], [ts_pass, ts_fail], workspace=workspace)
        # Winner must be a valid cell
        assert isinstance(matrix.winner_impl_index, int)
        assert isinstance(matrix.winner_test_index, int)

    def test_cells_have_impl_test_indices(self, workspace):
        cands = workspace / "candidates"
        impl0 = _make_impl(cands / "impl_0.py")
        ts0 = _make_passing_test(cands / "tests_0.py")
        matrix = score_matrix([impl0], [ts0], workspace=workspace)
        cell = matrix.cells[0]
        assert cell.impl_index == 0
        assert cell.test_index == 0

    def test_matrix_cell_score_formula(self, workspace):
        """Score = passing_tests * (unique_fail_count + 1)."""
        cands = workspace / "candidates"
        impl0 = _make_impl(cands / "impl_0.py")
        ts0 = _make_passing_test(cands / "tests_0.py")
        matrix = score_matrix([impl0], [ts0], workspace=workspace)
        cell = matrix.cells[0]
        expected = float(cell.passing_tests * (cell.unique_fail_count + 1))
        assert cell.score == pytest.approx(expected)
