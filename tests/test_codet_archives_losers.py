"""Tests for archive_losers in codet_triangulation."""

from __future__ import annotations

from pathlib import Path

import yaml
import pytest

from bob.orchestrator.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    MatrixCell,
    ScoredMatrix,
    archive_losers,
)


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


def _make_2x2_matrix(winner_impl: int = 0, winner_test: int = 0) -> ScoredMatrix:
    cells = [
        MatrixCell(impl_index=0, test_index=0, passing_tests=1, unique_fail_count=1, score=2.0, passed=True),
        MatrixCell(impl_index=0, test_index=1, passing_tests=0, unique_fail_count=0, score=0.0, passed=False),
        MatrixCell(impl_index=1, test_index=0, passing_tests=0, unique_fail_count=0, score=0.0, passed=False),
        MatrixCell(impl_index=1, test_index=1, passing_tests=0, unique_fail_count=1, score=0.0, passed=False),
    ]
    return ScoredMatrix(
        cells=cells,
        winner_impl_index=winner_impl,
        winner_test_index=winner_test,
        winner_score=2.0,
    )


def _impl(path: Path, idx: int) -> CandidateImpl:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"class Impl{idx}:\n    pass\n"
    path.write_text(content, encoding="utf-8")
    return CandidateImpl(index=idx, impl_path=path, content=content)


def _ts(path: Path, idx: int) -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"def test_{idx}():\n    assert True\n"
    path.write_text(content, encoding="utf-8")
    return CandidateTestSet(index=idx, framing="positive", test_path=path, content=content)


class TestArchiveLosersMovesCells:
    def test_variants_dir_created(self, workspace):
        feature_id = "feat-archive-basic"
        cands = workspace / "candidates"
        impls = [_impl(cands / f"impl_{i}.py", i) for i in range(2)]
        tests = [_ts(cands / f"tests_{j}.py", j) for j in range(2)]
        matrix = _make_2x2_matrix(winner_impl=0, winner_test=0)

        archive_losers(feature_id, matrix, impls, tests, workspace=workspace)

        variants_dir = workspace / "runs" / feature_id / "variants"
        assert variants_dir.exists()

    def test_loser_dirs_created(self, workspace):
        feature_id = "feat-archive-dirs"
        cands = workspace / "candidates"
        impls = [_impl(cands / f"impl_{i}.py", i) for i in range(2)]
        tests = [_ts(cands / f"tests_{j}.py", j) for j in range(2)]
        matrix = _make_2x2_matrix(winner_impl=0, winner_test=0)

        dirs = archive_losers(feature_id, matrix, impls, tests, workspace=workspace)

        # 2x2 matrix minus 1 winner = 3 losers
        assert len(dirs) == 3

    def test_winner_not_in_losers(self, workspace):
        feature_id = "feat-winner-excluded"
        cands = workspace / "candidates"
        impls = [_impl(cands / f"impl_{i}.py", i) for i in range(2)]
        tests = [_ts(cands / f"tests_{j}.py", j) for j in range(2)]
        matrix = _make_2x2_matrix(winner_impl=0, winner_test=0)

        dirs = archive_losers(feature_id, matrix, impls, tests, workspace=workspace)

        dir_names = [d.name for d in dirs]
        assert "impl_0_test_0" not in dir_names

    def test_each_loser_dir_contains_cell_meta(self, workspace):
        feature_id = "feat-meta-check"
        cands = workspace / "candidates"
        impls = [_impl(cands / f"impl_{i}.py", i) for i in range(2)]
        tests = [_ts(cands / f"tests_{j}.py", j) for j in range(2)]
        matrix = _make_2x2_matrix(winner_impl=0, winner_test=0)

        dirs = archive_losers(feature_id, matrix, impls, tests, workspace=workspace)

        for d in dirs:
            meta_path = d / "cell_meta.yaml"
            assert meta_path.exists(), f"Missing cell_meta.yaml in {d}"
            data = yaml.safe_load(meta_path.read_text())
            assert "impl_index" in data
            assert "test_index" in data
            assert "score" in data

    def test_returns_list_of_paths(self, workspace):
        feature_id = "feat-return-type"
        cands = workspace / "candidates"
        impls = [_impl(cands / "impl_0.py", 0)]
        tests = [_ts(cands / "tests_0.py", 0)]
        # 1x1 matrix — winner is the only cell, no losers
        cells = [MatrixCell(impl_index=0, test_index=0, passing_tests=1,
                            unique_fail_count=0, score=1.0, passed=True)]
        matrix = ScoredMatrix(cells=cells, winner_impl_index=0, winner_test_index=0, winner_score=1.0)

        dirs = archive_losers(feature_id, matrix, impls, tests, workspace=workspace)

        assert isinstance(dirs, list)
        assert len(dirs) == 0  # no losers in 1x1 matrix
