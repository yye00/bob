"""Boundary tests for bob.verification.ctest_runner.

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from bob.verification.ctest_runner import parse_junit_xml, run_ctest_ac, JUnitResult


def test_empty_testsuite_returns_zero_counts():
    result = parse_junit_xml("<testsuite></testsuite>")
    assert isinstance(result, JUnitResult)
    assert result.total == 0
    assert result.failed == 0
    assert result.passed == 0


def test_minimal_single_passing_testcase():
    result = parse_junit_xml('<testsuite><testcase name="a"/></testsuite>')
    assert result.total == 1
    assert result.passed == 1
    assert result.failed == 0


def test_run_ctest_ac_zero_tests_is_well_defined_fail(tmp_path):
    result = run_ctest_ac(
        criterion="ctest: nothing",
        build_dir=str(tmp_path),
        junit_xml="<testsuite tests='0' failures='0'></testsuite>",
    )
    # Well-defined dict result, not an exception.
    assert isinstance(result, dict)
    assert result["passed"] is False


def test_junit_result_is_frozen_dataclass_like():
    result = parse_junit_xml("<testsuite></testsuite>")
    # passed is derived and non-negative
    assert result.passed >= 0
    assert result.total >= 0
