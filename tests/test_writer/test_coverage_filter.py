"""Tests for the coverage-filter component (AC: test_coverage_filter).

Validates the third leg of the TestGen-LLM triple filter: the coverage heuristic.
Tests that _check_raises_coverage correctly distinguishes tests that reference
real code from vacuous no-op tests, and that reject_no_coverage_uplift raises
NoCoverageUpliftError when the heuristic fails.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.test_writer_agent import (
    NoCoverageUpliftError,
    _check_raises_coverage,
    emit_failing_tests,
    reject_no_coverage_uplift,
    triple_filter,
)
from test_writer import TestWriterAgent


class TestCheckRaisesCoverageBasic:
    def test_pytest_fail_call_passes_heuristic(self, tmp_path):
        """A test with pytest.fail() must pass the coverage heuristic."""
        with_fail = tmp_path / "test_fail.py"
        with_fail.write_text(
            "import pytest\n\ndef test_not_impl():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_fail) is True

    def test_only_assert_true_fails_heuristic(self, tmp_path):
        """A test with only 'assert True' must fail the coverage heuristic."""
        trivial = tmp_path / "test_trivial.py"
        trivial.write_text("def test_noop():\n    assert True\n", encoding="utf-8")
        assert _check_raises_coverage(trivial) is False

    def test_pass_only_body_fails_heuristic(self, tmp_path):
        """A test with only 'pass' in the body must fail the coverage heuristic."""
        pass_only = tmp_path / "test_pass.py"
        pass_only.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        assert _check_raises_coverage(pass_only) is False

    def test_non_pytest_import_passes_heuristic(self, tmp_path):
        """A test that imports a non-pytest module must pass the coverage heuristic."""
        with_import = tmp_path / "test_import.py"
        with_import.write_text(
            "import pathlib\nimport pytest\n\ndef test_x():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_import) is True

    def test_from_non_pytest_import_passes_heuristic(self, tmp_path):
        """A test using 'from somemod import ...' must pass the coverage heuristic."""
        with_from = tmp_path / "test_from.py"
        with_from.write_text(
            "from pathlib import Path\nimport pytest\n\ndef test_y():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_from) is True

    def test_nontrivial_assertion_passes_heuristic(self, tmp_path):
        """A test with a non-trivial assertion must pass the coverage heuristic."""
        with_assert = tmp_path / "test_assert.py"
        with_assert.write_text(
            "def test_value():\n    assert 1 + 1 == 3, 'expected fail'\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_assert) is True

    def test_pytest_raises_call_passes_heuristic(self, tmp_path):
        """A test using pytest.raises() must pass the coverage heuristic."""
        with_raises = tmp_path / "test_raises.py"
        with_raises.write_text(
            "import pytest\n\ndef test_z():\n    with pytest.raises(ValueError):\n        raise ValueError('x')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_raises) is True

    def test_empty_file_fails_heuristic(self, tmp_path):
        """An empty file has no coverage-raising content."""
        empty = tmp_path / "test_empty.py"
        empty.write_text("", encoding="utf-8")
        assert _check_raises_coverage(empty) is False

    def test_invalid_utf8_file_returns_false(self, tmp_path):
        """A file with invalid UTF-8 must return False (treated as unparseable)."""
        binary = tmp_path / "test_binary.py"
        binary.write_bytes(b"\xff\xfe bad bytes \x00")
        assert _check_raises_coverage(binary) is False


class TestRejectNoCoverageUplift:
    def test_does_not_raise_for_real_test(self, tmp_path):
        """reject_no_coverage_uplift must be silent for a test with real assertions."""
        real = tmp_path / "test_real.py"
        real.write_text(
            "import pytest\n\ndef test_it():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(real)  # must not raise

    def test_raises_for_trivial_test(self, tmp_path):
        """reject_no_coverage_uplift must raise NoCoverageUpliftError for trivial tests."""
        trivial = tmp_path / "test_trivial.py"
        trivial.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(trivial)

    def test_raises_for_assert_true_only_test(self, tmp_path):
        """reject_no_coverage_uplift must raise NoCoverageUpliftError for assert-True-only tests."""
        assert_true = tmp_path / "test_assert_true.py"
        assert_true.write_text("def test_noop():\n    assert True\n", encoding="utf-8")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(assert_true)

    def test_raises_when_ac_region_not_in_source(self, tmp_path):
        """When ac_region is given and not found in source, must raise NoCoverageUpliftError."""
        valid_test = tmp_path / "test_no_region.py"
        valid_test.write_text(
            "import pytest\n\ndef test_something():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError, match="my_special_function"):
            reject_no_coverage_uplift(valid_test, ac_region="my_special_function")

    def test_does_not_raise_when_ac_region_present(self, tmp_path):
        """When ac_region is present in source and heuristic passes, must not raise."""
        with_region = tmp_path / "test_with_region.py"
        with_region.write_text(
            "import pytest\nfrom bob.mymod import my_special_function\n\n"
            "def test_it():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(with_region, ac_region="my_special_function")  # must not raise


class TestTripleFilterCoverageCheck:
    def test_emitted_test_passes_coverage_filter(self, tmp_path):
        """All tests emitted by emit_failing_tests must pass the coverage heuristic."""
        acs = ["Function defined: bob.mymod.fn"]
        emitted = emit_failing_tests("feat-cov-filter", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].raises_coverage is True

    def test_filter_rejects_test_with_no_coverage(self, tmp_path):
        """A test with only 'pass' must be rejected by triple_filter."""
        acs = ["File exists: src/placeholder.py"]
        emitted = emit_failing_tests("feat-cov-reject", acs, workspace=tmp_path)
        emitted[0].test_path.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].accepted is False

    def test_filter_coverage_reason_mentions_coverage(self, tmp_path):
        """FilterResult.reason for a coverage failure must mention coverage or non-pytest symbol."""
        acs = ["File exists: src/mod.py"]
        emitted = emit_failing_tests("feat-cov-reason", acs, workspace=tmp_path)
        emitted[0].test_path.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        results = triple_filter(emitted, workspace=tmp_path)
        r = results[0]
        assert "coverage" in r.reason.lower() or "symbol" in r.reason.lower()

    def test_generate_gate_passed_true_for_coverage_compliant_tests(self, tmp_path):
        """generate_failing_tests must return gate_passed=True for standard ACs."""
        from bob.orchestrator.test_writer_agent import generate_failing_tests
        acs = ["File exists: src/a.py", "Function defined: bob.a.fn"]
        result = generate_failing_tests("feat-cov-gate", acs, workspace=tmp_path)
        assert result["gate_passed"] is True
        assert all(r.raises_coverage for r in result["filter_results"])

    def test_agent_filter_coverage_check(self, tmp_path):
        """TestWriterAgent.filter must reflect raises_coverage=True for emitted tests."""
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-cov-agent", ["pytest: tests/test_x.py"])
        results = agent.filter(emitted)
        assert all(r.raises_coverage for r in results), "All emitted tests should pass coverage heuristic"
