"""Tests for the coverage heuristic in the triple-filter (AC: test_ac_coverage).

Validates that the TestGen-LLM triple filter correctly evaluates whether a
test file raises coverage of the AC-named region — check 3 of 3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    NoCoverageUpliftError,
    _check_raises_coverage,
    emit_failing_tests,
    reject_no_coverage_uplift,
    triple_filter,
)


class TestAcCoverage:
    def test_emitted_test_raises_coverage_heuristic(self, tmp_path):
        """Tests emitted by emit_failing_tests must pass the coverage heuristic."""
        acs = ["Function defined: bob.mymod.my_fn"]
        emitted = emit_failing_tests("feat-cov-check", acs, workspace=tmp_path)
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

    def test_triple_filter_rejects_no_coverage_uplift(self, tmp_path):
        """triple_filter must reject a test that doesn't reference any non-pytest symbol."""
        acs = ["File exists: src/bob/placeholder.py"]
        emitted = emit_failing_tests("feat-cov-filter", acs, workspace=tmp_path)
        # Replace with a test that has no non-pytest references and no assertions
        emitted[0].test_path.write_text(
            "def test_noop():\n    pass\n",
            encoding="utf-8",
        )
        results = triple_filter(emitted, workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r.compiles
        # This test passes on stub (assert True missing, pass == green) but
        # it also has no coverage uplift — the filter might reject at step 2 or 3
        assert not r.accepted

    def test_reject_no_coverage_uplift_passes_for_real_test(self, tmp_path):
        """reject_no_coverage_uplift must not raise for a test with real assertions."""
        real = tmp_path / "test_real.py"
        real.write_text(
            "import pytest\ndef test_it():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(real)  # should not raise

    def test_reject_no_coverage_uplift_raises_for_trivial_test(self, tmp_path):
        """reject_no_coverage_uplift must raise NoCoverageUpliftError for trivial tests."""
        trivial = tmp_path / "test_trivial.py"
        trivial.write_text("def test_noop():\n    pass\n", encoding="utf-8")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(trivial)

    def test_reject_no_coverage_uplift_with_ac_region_present(self, tmp_path):
        """When ac_region is provided and present in source, no error is raised."""
        with_region = tmp_path / "test_region.py"
        with_region.write_text(
            "import pytest\n\ndef test_my_module():\n    # my_module.process\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        reject_no_coverage_uplift(with_region, ac_region="my_module")

    def test_reject_no_coverage_uplift_with_ac_region_absent(self, tmp_path):
        """When ac_region is provided but absent from source, NoCoverageUpliftError is raised."""
        without_region = tmp_path / "test_no_region.py"
        without_region.write_text(
            "import pytest\ndef test_something():\n    pytest.fail('red')\n",
            encoding="utf-8",
        )
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(without_region, ac_region="missing_module_xyz")
