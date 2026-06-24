"""Tests verifying the Coverage check of the test-writer sub-agent triple filter.

The triple filter's third check rejects tests that fail to raise coverage of
the AC-named region — tests with no non-pytest imports and no meaningful
assertions beyond ``assert True`` or ``pass``.
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.test_writer_agent import (
    NoCoverageUpliftError,
    _check_raises_coverage,
    reject_no_coverage_uplift,
)
from bob3.test_writer_subagent import generate_failing_tests


class TestCoverageFilterCheck:
    def test_trivial_assert_true_fails_coverage_check(self, tmp_path):
        """A test with only assert True must fail the coverage heuristic."""
        f = tmp_path / "test_trivial.py"
        f.write_text("def test_nothing():\n    assert True\n")
        assert _check_raises_coverage(f) is False

    def test_pass_body_fails_coverage_check(self, tmp_path):
        """A test with only pass must fail the coverage heuristic."""
        f = tmp_path / "test_pass.py"
        f.write_text("def test_nothing():\n    pass\n")
        assert _check_raises_coverage(f) is False

    def test_pytest_fail_passes_coverage_check(self, tmp_path):
        """A test with pytest.fail satisfies the coverage heuristic."""
        f = tmp_path / "test_fail.py"
        f.write_text("import pytest\n\ndef test_red():\n    pytest.fail('not yet')\n")
        assert _check_raises_coverage(f) is True

    def test_non_pytest_import_passes_coverage_check(self, tmp_path):
        """A test importing a non-pytest module passes the coverage heuristic."""
        f = tmp_path / "test_imports.py"
        f.write_text("import pathlib\n\ndef test_x():\n    assert pathlib.Path('.').exists()\n")
        assert _check_raises_coverage(f) is True

    def test_reject_no_coverage_uplift_raises_for_trivial_test(self, tmp_path):
        """reject_no_coverage_uplift must raise NoCoverageUpliftError for trivial tests."""
        f = tmp_path / "test_trivial_cov.py"
        f.write_text("def test_nothing():\n    assert True\n")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(f)

    def test_reject_no_coverage_uplift_silent_for_real_test(self, tmp_path):
        """reject_no_coverage_uplift must not raise for a test with a real import."""
        f = tmp_path / "test_real.py"
        f.write_text("import pathlib\n\ndef test_x():\n    assert pathlib.Path('.').exists()\n")
        reject_no_coverage_uplift(f)  # must not raise

    def test_reject_no_coverage_uplift_with_missing_ac_region_raises(self, tmp_path):
        """reject_no_coverage_uplift raises when ac_region is absent from test source."""
        f = tmp_path / "test_region.py"
        f.write_text("import pathlib\n\ndef test_x():\n    assert pathlib.Path('.').exists()\n")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(f, ac_region="missing_symbol_xyz")

    def test_reject_no_coverage_uplift_silent_when_ac_region_present(self, tmp_path):
        """reject_no_coverage_uplift must not raise when ac_region appears in test source."""
        f = tmp_path / "test_with_region.py"
        f.write_text(
            "import pathlib\n\n"
            "def test_x():\n"
            "    # references my_target_symbol\n"
            "    assert pathlib.Path('.').exists()\n"
        )
        reject_no_coverage_uplift(f, ac_region="my_target_symbol")  # must not raise

    def test_generated_structural_tests_pass_coverage_filter(self, tmp_path):
        """Tests emitted by generate_failing_tests for 'File exists' ACs pass coverage check."""
        acs = ["File exists: src/bob3/coverage_target.py"]
        result = generate_failing_tests("feat-cov-filter", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert fr.raises_coverage is True, (
                f"Expected coverage heuristic to pass for {fr.test_path}, "
                f"reason: {fr.reason!r}"
            )

    def test_filter_result_coverage_field_is_bool(self, tmp_path):
        """Each FilterResult must have raises_coverage as a bool."""
        acs = ["File exists: src/bob3/cov_bool_check.py"]
        result = generate_failing_tests("feat-cov-bool", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert isinstance(fr.raises_coverage, bool)
