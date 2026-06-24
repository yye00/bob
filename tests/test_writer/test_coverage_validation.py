"""Tests for coverage validation in the TestGen-LLM triple filter.

The third leg of the triple filter (coverage heuristic) rejects tests that
do not reference any non-pytest symbol — i.e., vacuous tests that couldn't
possibly provide coverage of the AC-named region.  This module validates that
the heuristic accepts and rejects the right tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    NoCoverageUpliftError,
    _check_raises_coverage,
    emit_failing_test,
    emit_failing_tests,
    reject_no_coverage_uplift,
    triple_filter,
)


class TestCoverageHeuristicOnEmittedTests:
    """Emitted tests from emit_failing_test must pass the coverage heuristic."""

    def test_emitted_test_passes_coverage_heuristic(self, tmp_path):
        """An emitted test must reference at least one non-pytest symbol."""
        et = emit_failing_test("feat-cov-heur", 0, "File exists: src/x.py", workspace=tmp_path)
        assert _check_raises_coverage(et.test_path) is True

    def test_emitted_test_accepted_by_triple_filter(self, tmp_path):
        et = emit_failing_test("feat-cov-accept", 0, "Function defined: bob.m.f", workspace=tmp_path)
        results = triple_filter([et], workspace=tmp_path)
        assert results[0].raises_coverage is True

    def test_multiple_emitted_tests_pass_coverage(self, tmp_path):
        acs = [
            "File exists: src/a.py",
            "Function defined: bob.m.g",
            "pytest: tests/test_c.py",
        ]
        emitted = emit_failing_tests("feat-cov-multi", acs, workspace=tmp_path)
        for et in emitted:
            assert _check_raises_coverage(et.test_path) is True, (
                f"Coverage heuristic failed for {et.test_path}"
            )


class TestCoverageHeuristicOnCustomFiles:
    """_check_raises_coverage correctly classifies custom test files."""

    def test_pytest_fail_passes_heuristic(self, tmp_path):
        f = tmp_path / "test_red.py"
        f.write_text(
            "import pytest\n\ndef test_not_impl():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(f) is True

    def test_assert_true_only_fails_heuristic(self, tmp_path):
        f = tmp_path / "test_trivial.py"
        f.write_text("def test_noop():\n    assert True\n", encoding="utf-8")
        assert _check_raises_coverage(f) is False

    def test_pass_only_body_fails_heuristic(self, tmp_path):
        f = tmp_path / "test_pass.py"
        f.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        assert _check_raises_coverage(f) is False

    def test_non_pytest_import_passes_heuristic(self, tmp_path):
        f = tmp_path / "test_import.py"
        f.write_text(
            "import pathlib\nimport pytest\n\ndef test_x():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(f) is True

    def test_from_import_non_pytest_passes_heuristic(self, tmp_path):
        f = tmp_path / "test_from.py"
        f.write_text(
            "from pathlib import Path\nimport pytest\n\ndef test_y():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(f) is True


class TestRejectNoCoverageUplift:
    """reject_no_coverage_uplift raises NoCoverageUpliftError for vacuous tests."""

    def test_raises_for_assert_true_only(self, tmp_path):
        f = tmp_path / "test_trivial.py"
        f.write_text("def test_noop():\n    assert True\n", encoding="utf-8")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(f)

    def test_passes_for_pytest_fail(self, tmp_path):
        f = tmp_path / "test_red.py"
        f.write_text(
            "import pytest\n\ndef test_x():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(f)  # must not raise

    def test_raises_when_ac_region_not_referenced(self, tmp_path):
        f = tmp_path / "test_no_region.py"
        f.write_text(
            "import pytest\n\ndef test_x():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(f, ac_region="bob.my_missing_module")

    def test_passes_when_ac_region_is_referenced(self, tmp_path):
        f = tmp_path / "test_region.py"
        f.write_text(
            "import bob.some_module\nimport pytest\n\ndef test_x():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(f, ac_region="bob.some_module")  # must not raise


class TestTripleFilterCoverageIntegration:
    """triple_filter correctly populates raises_coverage on FilterResult."""

    def test_emitted_test_has_raises_coverage_true(self, tmp_path):
        et = emit_failing_test("feat-cov-int", 0, "File exists: src/x.py", workspace=tmp_path)
        results = triple_filter([et], workspace=tmp_path)
        assert results[0].raises_coverage is True

    def test_vacuous_test_has_raises_coverage_false(self, tmp_path):
        """A manually written vacuous test must have raises_coverage=False."""
        from bob.orchestrator.test_writer_agent import EmittedTest
        vacuous = tmp_path / "test_vac.py"
        vacuous.write_text("def test_noop():\n    assert True\n", encoding="utf-8")
        et = EmittedTest(
            ac_index=0,
            ac_id="ac_0",
            ac_text="File exists: src/x.py",
            test_path=vacuous,
            feature_id="feat-cov-vac",
        )
        results = triple_filter([et], workspace=tmp_path)
        assert results[0].raises_coverage is False
        assert results[0].accepted is False
