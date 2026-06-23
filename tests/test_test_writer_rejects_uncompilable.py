"""Tests for triple_filter — rejects uncompilable and mysteriously-passing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import (
    EmittedTest,
    FilterResult,
    emit_failing_tests,
    triple_filter,
)


class TestTripleFilterAcceptsGoodTests:
    def test_accepts_properly_failing_test(self, tmp_path):
        acs = ["File exists: src/realmod.py"]
        emitted = emit_failing_tests("feat-filter-ok", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r.compiles is True
        assert r.fails_on_stub is True
        assert r.accepted is True

    def test_returns_filter_result_list(self, tmp_path):
        acs = ["Function defined: bob3.core.fn"]
        emitted = emit_failing_tests("feat-type-filter", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert all(isinstance(r, FilterResult) for r in results)

    def test_one_result_per_emitted_test(self, tmp_path):
        acs = ["pytest: a.py", "pytest: b.py", "File exists: c.py"]
        emitted = emit_failing_tests("feat-count", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == len(emitted)

    def test_empty_input_returns_empty(self, tmp_path):
        results = triple_filter([], workspace=tmp_path)
        assert results == []


class TestTripleFilterRejectsUncompilable:
    def test_rejects_syntax_error(self, tmp_path):
        bad_file = tmp_path / "test_bad_syntax.py"
        bad_file.write_text("def test_x(\n    pass\n", encoding="utf-8")
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_bad",
            ac_text="File exists: src/bad.py",
            test_path=bad_file,
            feature_id="feat-syntax",
        )
        results = triple_filter([et], workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r.compiles is False
        assert r.accepted is False
        assert "SyntaxError" in r.reason or "uncompilable" in r.reason.lower()

    def test_accepted_false_when_not_compiles(self, tmp_path):
        bad_file = tmp_path / "test_bad2.py"
        bad_file.write_text("import (\nfail\n", encoding="utf-8")
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_bad2",
            ac_text="pytest: tests/test_x.py",
            test_path=bad_file,
            feature_id="feat-bad2",
        )
        results = triple_filter([et], workspace=tmp_path)
        assert results[0].accepted is False


class TestTripleFilterRejectsMysteriouslyPassing:
    def test_rejects_test_that_passes_vacuously(self, tmp_path):
        # A test with assert True always passes — should be rejected
        vacuous = tmp_path / "test_vacuous.py"
        vacuous.write_text(
            "def test_always_passes():\n    assert True\n",
            encoding="utf-8",
        )
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_vacuous",
            ac_text="File exists: src/x.py",
            test_path=vacuous,
            feature_id="feat-vacuous",
        )
        results = triple_filter([et], workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        # Either fails_on_stub=False (correctly runs and passes) OR raises_coverage=False
        assert r.accepted is False

    def test_reason_populated_when_rejected(self, tmp_path):
        bad_file = tmp_path / "test_uncompilable_reason.py"
        bad_file.write_text("def test(:\n    pass\n", encoding="utf-8")
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_reason",
            ac_text="pytest: tests/test_r.py",
            test_path=bad_file,
            feature_id="feat-reason",
        )
        results = triple_filter([et], workspace=tmp_path)
        assert results[0].reason != ""


class TestTripleFilterCoverageHeuristic:
    def test_test_with_non_pytest_import_raises_coverage(self, tmp_path):
        good = tmp_path / "test_good_import.py"
        good.write_text(
            "import os\nimport pytest\ndef test_x():\n    pytest.fail('not done')\n",
            encoding="utf-8",
        )
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0_import",
            ac_text="File exists: src/y.py",
            test_path=good,
            feature_id="feat-import",
        )
        results = triple_filter([et], workspace=tmp_path)
        assert results[0].raises_coverage is True

    def test_template_generated_test_passes_coverage(self, tmp_path):
        acs = ["File exists: src/cov.py"]
        emitted = emit_failing_tests("feat-cov", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert results[0].raises_coverage is True
