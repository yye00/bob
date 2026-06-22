"""Tests for TestWriterAgent — coverage heuristic (AC: test_ac_coverage).

Validates that the TestWriterAgent correctly evaluates whether a test file
raises coverage of the AC-named region — check 3 of 3 in the triple filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_writer import TestWriterAgent
from bob3.orchestrator.test_writer_agent import (
    NoCoverageUpliftError,
    _check_raises_coverage,
    reject_no_coverage_uplift,
)


class TestAcCoverage:
    def test_emitted_test_raises_coverage_heuristic(self, tmp_path):
        """Tests emitted by TestWriterAgent.emit must pass the coverage heuristic."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["Function defined: bob3.mymod.my_fn"]
        emitted = agent.emit("feat-cov-check", acs)
        assert emitted, "expected at least one emitted test"
        for et in emitted:
            assert _check_raises_coverage(et.test_path), (
                f"{et.test_path} should pass coverage heuristic (pytest.fail call present)"
            )

    def test_trivial_assert_true_test_fails_coverage(self, tmp_path):
        """A test with only 'assert True' must fail the coverage heuristic."""
        trivial = tmp_path / "test_trivial.py"
        trivial.write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
        assert not _check_raises_coverage(trivial)

    def test_non_pytest_import_passes_coverage(self, tmp_path):
        """A test importing a non-pytest module must pass the coverage heuristic."""
        with_import = tmp_path / "test_with_import.py"
        with_import.write_text(
            "import pathlib\nimport pytest\ndef test_something():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_import)

    def test_pytest_fail_call_passes_coverage(self, tmp_path):
        """A test calling pytest.fail() passes the coverage heuristic."""
        with_fail = tmp_path / "test_pytest_fail.py"
        with_fail.write_text(
            "import pytest\ndef test_not_impl():\n    pytest.fail('not implemented')\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(with_fail)

    def test_nontrivial_assertion_passes_coverage(self, tmp_path):
        """A test with a non-trivial assertion must pass the coverage heuristic."""
        asserting = tmp_path / "test_asserting.py"
        asserting.write_text(
            "def test_value():\n    assert 1 + 1 == 3, 'expected fail'\n",
            encoding="utf-8",
        )
        assert _check_raises_coverage(asserting)

    def test_filter_rejects_no_coverage_uplift(self, tmp_path):
        """filter() must reject a test that doesn't reference any non-pytest symbol."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/bob3/placeholder.py"]
        emitted = agent.emit("feat-cov-filter", acs)
        # Replace with a test that has no non-pytest references and no assertions
        emitted[0].test_path.write_text(
            "def test_noop():\n    pass\n",
            encoding="utf-8",
        )
        results = agent.filter(emitted)
        assert len(results) == 1
        r = results[0]
        assert not r.accepted

    def test_reject_no_coverage_uplift_passes_for_real_test(self, tmp_path):
        """reject_no_coverage_uplift must not raise for a test with real assertions."""
        real = tmp_path / "test_real.py"
        real.write_text(
            "import pytest\ndef test_it():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(real)

    def test_reject_no_coverage_uplift_raises_for_trivial_test(self, tmp_path):
        """reject_no_coverage_uplift must raise NoCoverageUpliftError for trivial tests."""
        trivial = tmp_path / "test_trivial.py"
        trivial.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(trivial)

    def test_generate_gate_passes_for_coverage_compliant_test(self, tmp_path):
        """generate() returns gate_passed=True when tests pass all three filter checks."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-cov-gate", ["Function defined: bob3.x.fn"])
        assert result["gate_passed"] is True
        assert all(r.raises_coverage for r in result["filter_results"])
