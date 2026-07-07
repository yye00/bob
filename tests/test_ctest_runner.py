"""Tests for bob.verification.ctest_runner.

Covers JUnit-XML parsing and the ctest AC runner with per-feature scoping.
The runner is exercised without a real CMake build by injecting the JUnit XML
via the ``junit_xml`` argument (the same shape ctest's ``--output-junit``
produces), so these tests do not require ctest/cmake on PATH.
"""

from __future__ import annotations

import textwrap

import pytest

from bob.verification.ctest_runner import (
    parse_junit_xml,
    run_ctest_ac,
    build_ctest_command,
    JUnitResult,
)


# --------------------------------------------------------------------------- #
# parse_junit_xml
# --------------------------------------------------------------------------- #

_ALL_PASS = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="rccl" tests="3" failures="0" skipped="0">
      <testcase name="AllReduce.Sum" classname="rccl" time="0.1"/>
      <testcase name="AllReduce.Max" classname="rccl" time="0.2"/>
      <testcase name="Broadcast.Basic" classname="rccl" time="0.3"/>
    </testsuite>
    """
)

_ONE_FAIL = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="rccl" tests="2" failures="1" skipped="0">
      <testcase name="AllReduce.Sum" classname="rccl">
        <failure message="assertion failed">expected 6 got 5</failure>
      </testcase>
      <testcase name="AllReduce.Max" classname="rccl"/>
    </testsuite>
    """
)

_WITH_SKIP = textwrap.dedent(
    """\
    <?xml version="1.0"?>
    <testsuite name="rccl" tests="3" failures="0" skipped="1">
      <testcase name="A.one"/>
      <testcase name="A.two"><skipped/></testcase>
      <testcase name="A.three"/>
    </testsuite>
    """
)

_TESTSUITES_WRAPPER = textwrap.dedent(
    """\
    <?xml version="1.0"?>
    <testsuites>
      <testsuite name="s1" tests="1" failures="0" skipped="0">
        <testcase name="s1.a"/>
      </testsuite>
      <testsuite name="s2" tests="2" failures="1" skipped="0">
        <testcase name="s2.a"><failure/></testcase>
        <testcase name="s2.b"/>
      </testsuite>
    </testsuites>
    """
)


def test_parse_all_pass():
    result = parse_junit_xml(_ALL_PASS)
    assert isinstance(result, JUnitResult)
    assert result.total == 3
    assert result.failed == 0
    assert result.skipped == 0
    assert result.passed == 3


def test_parse_one_failure_counted_from_testcases():
    result = parse_junit_xml(_ONE_FAIL)
    assert result.total == 2
    assert result.failed == 1
    assert result.passed == 1


def test_parse_skipped():
    result = parse_junit_xml(_WITH_SKIP)
    assert result.total == 3
    assert result.skipped == 1
    assert result.failed == 0
    # passed = total - failed - skipped
    assert result.passed == 2


def test_parse_testsuites_wrapper_aggregates():
    result = parse_junit_xml(_TESTSUITES_WRAPPER)
    assert result.total == 3
    assert result.failed == 1
    assert result.passed == 2


def test_parse_counts_failures_from_child_elements_when_attrs_absent():
    xml = (
        '<testsuite><testcase name="a"><failure/></testcase>'
        '<testcase name="b"/></testsuite>'
    )
    result = parse_junit_xml(xml)
    assert result.total == 2
    assert result.failed == 1


# --------------------------------------------------------------------------- #
# run_ctest_ac (injected JUnit XML — no real build)
# --------------------------------------------------------------------------- #

def test_run_ctest_ac_pass(tmp_path):
    result = run_ctest_ac(
        criterion="ctest: rccl_allreduce",
        build_dir=str(tmp_path),
        junit_xml=_ALL_PASS,
    )
    assert result["passed"] is True
    assert "3" in result["reason"]


def test_run_ctest_ac_fail_on_failure(tmp_path):
    result = run_ctest_ac(
        criterion="ctest: rccl_allreduce",
        build_dir=str(tmp_path),
        junit_xml=_ONE_FAIL,
    )
    assert result["passed"] is False
    assert "1 failed" in result["reason"]


def test_run_ctest_ac_fail_when_zero_tests_ran(tmp_path):
    empty = '<testsuite name="rccl" tests="0" failures="0" skipped="0"></testsuite>'
    result = run_ctest_ac(
        criterion="ctest: rccl_allreduce",
        build_dir=str(tmp_path),
        junit_xml=empty,
    )
    # N>0 tests must actually run
    assert result["passed"] is False
    assert "0" in result["reason"] or "no test" in result["reason"].lower()


def test_run_ctest_ac_shape_matches_pytest_handler(tmp_path):
    result = run_ctest_ac(
        criterion="ctest: rccl",
        build_dir=str(tmp_path),
        junit_xml=_ALL_PASS,
    )
    assert "name" in result
    assert "passed" in result
    assert isinstance(result["passed"], bool)


def test_run_ctest_ac_baseline_demotes_preexisting_failure(tmp_path):
    # A failure present in the baseline should not fail the feature.
    baseline = parse_junit_xml(_ONE_FAIL)
    result = run_ctest_ac(
        criterion="ctest: rccl",
        build_dir=str(tmp_path),
        junit_xml=_ONE_FAIL,
        baseline=baseline,
    )
    assert result["passed"] is True
    assert result.get("severity") == "warning"


# --------------------------------------------------------------------------- #
# build_ctest_command — per-feature scoping
# --------------------------------------------------------------------------- #

def test_build_ctest_command_scopes_with_regex():
    cmd = build_ctest_command(build_dir="/tmp/build", regex="rccl_allreduce",
                              junit_out="/tmp/out.xml")
    assert "ctest" in cmd[0]
    assert "-R" in cmd
    assert "rccl_allreduce" in cmd
    assert "--output-junit" in cmd
    assert "/tmp/out.xml" in cmd
    assert "--test-dir" in cmd


def test_build_ctest_command_never_runs_whole_world():
    # A scoped command must always include -R with a non-empty regex.
    cmd = build_ctest_command(build_dir="/tmp/build", regex="myfeature",
                              junit_out="/tmp/out.xml")
    idx = cmd.index("-R")
    assert cmd[idx + 1] == "myfeature"
