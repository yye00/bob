"""Tests for persist_winning_cell in codet_triangulation."""

from __future__ import annotations

from pathlib import Path

import yaml
import pytest

from bob3.orchestrator.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    ScoredMatrix,
    persist_winning_cell,
)


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


def _make_scored_matrix(impl_idx: int = 0, test_idx: int = 0, score: float = 2.0) -> ScoredMatrix:
    cells = [
        MatrixCell(
            impl_index=impl_idx,
            test_index=test_idx,
            passing_tests=1,
            unique_fail_count=1,
            score=score,
            passed=True,
        )
    ]
    return ScoredMatrix(
        cells=cells,
        winner_impl_index=impl_idx,
        winner_test_index=test_idx,
        winner_score=score,
    )


def _impl(path: Path) -> CandidateImpl:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("class I:\n    pass\n", encoding="utf-8")
    return CandidateImpl(index=0, impl_path=path, content="class I:\n    pass\n")


def _ts(path: Path) -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "def test_x():\n    assert True\n"
    path.write_text(content, encoding="utf-8")
    return CandidateTestSet(index=0, framing="positive", test_path=path, content=content)


class TestPersistWinnerCreatesFile:
    def test_winner_yaml_created(self, workspace):
        feature_id = "feat-persist-test"
        cands = workspace / "candidates"
        impl = _impl(cands / "impl_0.py")
        ts = _ts(cands / "tests_0.py")
        matrix = _make_scored_matrix()

        path = persist_winning_cell(
            feature_id, matrix, [impl], [ts], workspace=workspace
        )

        assert path.exists()
        assert path.name == "winner.yaml"

    def test_winner_yaml_in_correct_directory(self, workspace):
        feature_id = "feat-dir-check"
        cands = workspace / "candidates"
        impl = _impl(cands / "impl_0.py")
        ts = _ts(cands / "tests_0.py")
        matrix = _make_scored_matrix()

        path = persist_winning_cell(
            feature_id, matrix, [impl], [ts], workspace=workspace
        )

        expected_dir = workspace / "runs" / feature_id
        assert path.parent == expected_dir

    def test_winner_yaml_contains_feature_id(self, workspace):
        feature_id = "feat-content-check"
        cands = workspace / "candidates"
        impl = _impl(cands / "impl_0.py")
        ts = _ts(cands / "tests_0.py")
        matrix = _make_scored_matrix()

        path = persist_winning_cell(
            feature_id, matrix, [impl], [ts], workspace=workspace
        )

        data = yaml.safe_load(path.read_text())
        assert data["feature_id"] == feature_id

    def test_winner_yaml_contains_score(self, workspace):
        feature_id = "feat-score-check"
        cands = workspace / "candidates"
        impl = _impl(cands / "impl_0.py")
        ts = _ts(cands / "tests_0.py")
        matrix = _make_scored_matrix(score=3.5)

        path = persist_winning_cell(
            feature_id, matrix, [impl], [ts], workspace=workspace
        )

        data = yaml.safe_load(path.read_text())
        assert data["winner"]["score"] == pytest.approx(3.5)

    def test_winner_yaml_contains_impl_and_test_indices(self, workspace):
        feature_id = "feat-indices-check"
        cands = workspace / "candidates"
        impl = _impl(cands / "impl_0.py")
        ts = _ts(cands / "tests_0.py")
        matrix = _make_scored_matrix(impl_idx=0, test_idx=0)

        path = persist_winning_cell(
            feature_id, matrix, [impl], [ts], workspace=workspace
        )

        data = yaml.safe_load(path.read_text())
        assert data["winner"]["impl_index"] == 0
        assert data["winner"]["test_index"] == 0

    def test_winner_yaml_contains_matrix_size(self, workspace):
        feature_id = "feat-matrix-size"
        cands = workspace / "candidates"
        impl = _impl(cands / "impl_0.py")
        ts = _ts(cands / "tests_0.py")
        matrix = _make_scored_matrix()

        path = persist_winning_cell(
            feature_id, matrix, [impl], [ts], workspace=workspace
        )

        data = yaml.safe_load(path.read_text())
        assert data["matrix_size"]["n_impls"] == 1
        assert data["matrix_size"]["n_tests"] == 1
