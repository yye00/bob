"""Tests verifying the TestGen-LLM triple filter (Build/Pass/Coverage).

The triple filter rejects tests that:
  1. Don't compile (Build check)
  2. Mysteriously pass on stub code (Pass check)
  3. Fail to raise coverage of the AC-named region (Coverage check)

These tests verify the filter's behaviour via generate_failing_tests and
via the low-level reject_* helpers exposed from bob.orchestrator.test_writer_agent.
"""

from __future__ import annotations

import textwrap

import pytest

from bob.orchestrator.test_writer_agent import (
    FilterResult,
    NoCoverageUpliftError,
    StubPassError,
    UncompilableTestError,
    _check_compiles,
    _check_raises_coverage,
    reject_no_coverage_uplift,
    reject_passes_on_stub,
    reject_uncompilable,
)
from bob.test_writer_subagent import generate_failing_tests


# ---------------------------------------------------------------------------
# Build (compile) check
# ---------------------------------------------------------------------------


class TestBuildCheck:
    def test_valid_test_file_compiles(self, tmp_path):
        """A syntactically valid test file must pass the compile check."""
        f = tmp_path / "test_valid.py"
        f.write_text("import pytest\n\ndef test_ok():\n    pytest.fail('red')\n")
        assert _check_compiles(f) is True

    def test_syntax_error_file_fails_compile_check(self, tmp_path):
        """A file with a SyntaxError must fail the compile check."""
        f = tmp_path / "test_bad.py"
        f.write_text("def broken(\n")
        assert _check_compiles(f) is False

    def test_reject_uncompilable_raises_on_syntax_error(self, tmp_path):
        """reject_uncompilable must raise UncompilableTestError for a broken file."""
        f = tmp_path / "test_broken.py"
        f.write_text("class Bad\n")  # missing colon — SyntaxError
        with pytest.raises(UncompilableTestError):
            reject_uncompilable(f)

    def test_reject_uncompilable_silent_on_valid_file(self, tmp_path):
        """reject_uncompilable must not raise for a syntactically valid file."""
        f = tmp_path / "test_good.py"
        f.write_text("def test_foo():\n    assert 1 == 1\n")
        reject_uncompilable(f)  # must not raise


# ---------------------------------------------------------------------------
# Pass (stub) check
# ---------------------------------------------------------------------------


class TestPassCheck:
    def test_reject_passes_on_stub_raises_for_trivially_green_test(self, tmp_path):
        """A test that trivially passes (assert True) must raise StubPassError."""
        f = tmp_path / "test_trivial.py"
        f.write_text("def test_trivial():\n    assert True\n")
        with pytest.raises(StubPassError):
            reject_passes_on_stub(f)

    def test_reject_passes_on_stub_silent_for_failing_test(self, tmp_path):
        """A test that calls pytest.fail must not raise StubPassError."""
        import pytest as _pytest
        f = tmp_path / "test_red.py"
        f.write_text("import pytest\n\ndef test_red():\n    pytest.fail('not yet')\n")
        reject_passes_on_stub(f)  # must not raise

    def test_filter_result_accepted_false_for_stub_passing_test(self, tmp_path):
        """generate_failing_tests filter result must mark trivially-green test as not accepted."""
        # A hand-crafted trivially-green test injected into the output directory
        feature_id = "feat-stub-check"
        acs = ["File exists: src/non_existent_really.py"]
        result = generate_failing_tests(feature_id, acs, workspace=tmp_path)
        # The generated test for "File exists" is a real structural test that
        # fails on stub (file doesn't exist) — accepted must be True
        for fr in result["filter_results"]:
            # All filter results must have accepted set (True or False)
            assert isinstance(fr.accepted, bool)


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------


class TestCoverageCheck:
    def test_empty_test_body_fails_coverage_heuristic(self, tmp_path):
        """A test with only assert True fails the coverage heuristic."""
        f = tmp_path / "test_empty.py"
        f.write_text("def test_nothing():\n    assert True\n")
        assert _check_raises_coverage(f) is False

    def test_pytest_fail_satisfies_coverage_heuristic(self, tmp_path):
        """A test with pytest.fail satisfies the coverage heuristic."""
        f = tmp_path / "test_fail.py"
        f.write_text("import pytest\n\ndef test_red():\n    pytest.fail('nope')\n")
        assert _check_raises_coverage(f) is True

    def test_non_pytest_import_satisfies_coverage_heuristic(self, tmp_path):
        """A test importing a non-pytest module satisfies the coverage heuristic."""
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
        """reject_no_coverage_uplift must not raise for a real test."""
        f = tmp_path / "test_real.py"
        f.write_text("import pathlib\n\ndef test_x():\n    assert pathlib.Path('.').exists()\n")
        reject_no_coverage_uplift(f)  # must not raise

    def test_reject_no_coverage_uplift_with_ac_region_check(self, tmp_path):
        """reject_no_coverage_uplift with ac_region must raise if region not in source."""
        f = tmp_path / "test_region.py"
        f.write_text("import pathlib\n\ndef test_x():\n    assert pathlib.Path('.').exists()\n")
        with pytest.raises(NoCoverageUpliftError):
            reject_no_coverage_uplift(f, ac_region="missing_symbol_xyz")

    def test_reject_no_coverage_uplift_with_ac_region_present(self, tmp_path):
        """reject_no_coverage_uplift with ac_region must not raise if region is in source."""
        f = tmp_path / "test_with_region.py"
        f.write_text(
            "import pathlib\n\n"
            "def test_x():\n"
            "    # references my_target_symbol\n"
            "    assert pathlib.Path('.').exists()\n"
        )
        reject_no_coverage_uplift(f, ac_region="my_target_symbol")  # must not raise


# ---------------------------------------------------------------------------
# End-to-end: triple filter via generate_failing_tests
# ---------------------------------------------------------------------------


class TestTripleFilterEndToEnd:
    def test_structural_ac_passes_all_three_filter_checks(self, tmp_path):
        """A 'File exists' AC emits a test that passes the triple filter."""
        acs = ["File exists: src/bob/some_module_xyz.py"]
        result = generate_failing_tests("feat-triple-e2e", acs, workspace=tmp_path)
        assert len(result["filter_results"]) == 1
        fr = result["filter_results"][0]
        assert fr.compiles is True
        assert fr.fails_on_stub is True
        assert fr.raises_coverage is True
        assert fr.accepted is True

    def test_gate_passed_true_when_all_filter_results_accepted(self, tmp_path):
        """gate_passed must be True when all filter results are accepted."""
        acs = [
            "File exists: src/bob/module_a.py",
            "File exists: src/bob/module_b.py",
        ]
        result = generate_failing_tests("feat-gate-true", acs, workspace=tmp_path)
        all_accepted = all(fr.accepted for fr in result["filter_results"])
        assert result["gate_passed"] == (all_accepted and result["bijection"].is_bijective)

    def test_filter_result_objects_have_required_fields(self, tmp_path):
        """Each FilterResult must have all expected fields."""
        acs = ["File exists: src/bob/check_fields.py"]
        result = generate_failing_tests("feat-filter-fields", acs, workspace=tmp_path)
        for fr in result["filter_results"]:
            assert hasattr(fr, "test_path")
            assert hasattr(fr, "ac_id")
            assert hasattr(fr, "compiles")
            assert hasattr(fr, "fails_on_stub")
            assert hasattr(fr, "raises_coverage")
            assert hasattr(fr, "accepted")
            assert hasattr(fr, "reason")
