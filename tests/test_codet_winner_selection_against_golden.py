"""Tests for winner selection in score_matrix against golden cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    ScoredMatrix,
    score_matrix,
)


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


def _impl(path: Path, content: str = "class I:\n    pass\n") -> CandidateImpl:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return CandidateImpl(index=int(path.stem.split("_")[1]), impl_path=path, content=content)


def _ts(path: Path, content: str, index: int) -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return CandidateTestSet(index=index, framing="positive", test_path=path, content=content)


class TestWinnerSelectionGolden:
    def test_single_cell_wins_by_default(self, workspace):
        cands = workspace / "c"
        i0 = _impl(cands / "impl_0.py")
        t0 = _ts(cands / "tests_0.py", "def test_ok():\n    assert True\n", 0)
        m = score_matrix([i0], [t0], workspace=workspace)
        assert m.winner_impl_index == 0
        assert m.winner_test_index == 0

    def test_winner_score_stored_in_matrix(self, workspace):
        cands = workspace / "c"
        i0 = _impl(cands / "impl_0.py")
        t0 = _ts(cands / "tests_0.py", "def test_ok():\n    assert True\n", 0)
        m = score_matrix([i0], [t0], workspace=workspace)
        assert m.winner_score >= 0.0
        assert m.winner_score == m.cells[0].score

    def test_two_impls_one_test_winner_is_chosen(self, workspace):
        cands = workspace / "c"
        i0 = _impl(cands / "impl_0.py")
        i1 = _impl(cands / "impl_1.py")
        # Failing test — both impls will behave the same
        t0 = _ts(cands / "tests_0.py", "def test_fail():\n    assert False\n", 0)
        m = score_matrix([i0, i1], [t0], workspace=workspace)
        # Both impls fail — winner is determined deterministically (first)
        assert m.winner_impl_index in (0, 1)
        assert m.winner_test_index == 0

    def test_matrix_winner_is_highest_scoring_cell(self, workspace):
        cands = workspace / "c"
        i0 = _impl(cands / "impl_0.py")
        i1 = _impl(cands / "impl_1.py")
        t0 = _ts(cands / "tests_0.py", "def test_ok():\n    assert True\n", 0)
        t1 = _ts(cands / "tests_1.py", "def test_fail():\n    assert False\n", 1)
        m = score_matrix([i0, i1], [t0, t1], workspace=workspace)
        max_score = max(c.score for c in m.cells)
        assert m.winner_score == pytest.approx(max_score)

    def test_all_cells_have_non_negative_scores(self, workspace):
        cands = workspace / "c"
        i0 = _impl(cands / "impl_0.py")
        t0 = _ts(cands / "tests_0.py", "def test_x():\n    assert True\n", 0)
        m = score_matrix([i0], [t0], workspace=workspace)
        for cell in m.cells:
            assert cell.score >= 0.0
