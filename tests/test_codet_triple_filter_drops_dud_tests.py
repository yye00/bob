"""Tests for triple_filter in codet_triangulation — drops dud test sets."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.codet_triangulation import (
    CandidateTestSet,
    TripleFilterResult,
    triple_filter,
)


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


def _make_ts(path: Path, content: str, index: int = 0, framing: str = "positive") -> CandidateTestSet:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return CandidateTestSet(index=index, framing=framing, test_path=path, content=content)


class TestTripleFilterRejectsUncompilable:
    def test_syntax_error_rejected(self, workspace):
        bad = "def test_broken(\n    assert True\n"
        ts = _make_ts(workspace / "tests_0.py", bad)
        results = triple_filter([ts], workspace=workspace)
        assert len(results) == 1
        r = results[0]
        assert not r.compiles
        assert not r.accepted
        assert "SyntaxError" in r.reason or "rejected" in r.reason.lower()


class TestTripleFilterRejectsVacuous:
    def test_always_passing_test_rejected(self, workspace):
        # A test that always passes on any stub (vacuous)
        vacuous = "def test_always_passes():\n    assert True\n"
        ts = _make_ts(workspace / "tests_0.py", vacuous)
        results = triple_filter([ts], workspace=workspace)
        assert len(results) == 1
        r = results[0]
        assert r.compiles
        assert not r.fails_on_stub
        assert not r.accepted


class TestTripleFilterRejectsNoCoverage:
    def test_test_with_only_pytest_import_rejected(self, workspace):
        # Compiles and fails but imports only pytest — no coverage uplift
        no_cov = "import pytest\n\ndef test_no_coverage():\n    assert False\n"
        ts = _make_ts(workspace / "tests_0.py", no_cov)
        results = triple_filter([ts], workspace=workspace)
        assert len(results) == 1
        r = results[0]
        assert r.compiles
        # fails on stub (assert False always fails)
        assert r.fails_on_stub
        # no external imports → rejected
        assert not r.raises_coverage
        assert not r.accepted


class TestTripleFilterAcceptsGoodTest:
    def test_test_with_external_import_accepted(self, workspace):
        good = (
            "import os\n\n"
            "def test_with_real_import():\n"
            "    assert False, 'deliberately failing'\n"
        )
        ts = _make_ts(workspace / "tests_0.py", good)
        results = triple_filter([ts], workspace=workspace)
        assert len(results) == 1
        r = results[0]
        assert r.compiles
        assert r.fails_on_stub
        assert r.raises_coverage
        assert r.accepted


class TestTripleFilterReturnsOneResultPerInput:
    def test_result_count_matches_input(self, workspace):
        tests = []
        for i in range(4):
            src = f"def test_{i}():\n    assert False\n"
            ts = _make_ts(workspace / f"tests_{i}.py", src, index=i)
            tests.append(ts)
        results = triple_filter(tests, workspace=workspace)
        assert len(results) == 4

    def test_result_indices_match_input(self, workspace):
        src = "def test_x():\n    assert False\n"
        ts = _make_ts(workspace / "tests_2.py", src, index=2)
        results = triple_filter([ts], workspace=workspace)
        assert results[0].test_index == 2
