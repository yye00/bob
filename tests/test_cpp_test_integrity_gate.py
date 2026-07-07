"""C++ test-integrity gate — DISABLED_/GTEST_SKIP/ctest-drop anti-cheat.

A C++ subagent can hide failures without touching stub bodies by:
  * renaming a gtest to the ``DISABLED_`` prefix,
  * inserting ``GTEST_SKIP()`` in the body,
  * dropping a test from the ctest set (``add_test`` in CTestTestfile.cmake).

None of these are visible to bob's Python-shaped gates. This gate detects them.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bob.cpp_test_integrity_gate import (
    check_ctest_set_diff,
    check_disabled_tests_pass,
    check_test_integrity,
    find_disabled_tests,
    parse_gtest_list_tests,
    parse_gtest_xml_skipped,
    parse_ctest_add_tests,
)


# ---- parse_gtest_list_tests / find_disabled_tests ----

LIST_OUTPUT = """\
MathTest.
  Adds
  Subtracts
  DISABLED_SlowMultiply
DISABLED_LegacySuite.
  OldCase
"""


def test_parse_gtest_list_tests_returns_fully_qualified_names():
    names = parse_gtest_list_tests(LIST_OUTPUT)
    assert "MathTest.Adds" in names
    assert "MathTest.Subtracts" in names
    assert "MathTest.DISABLED_SlowMultiply" in names
    # A suite-level DISABLED_ prefix disables every test under it.
    assert "DISABLED_LegacySuite.OldCase" in names


def test_find_disabled_tests_detects_test_level_prefix():
    disabled = find_disabled_tests(LIST_OUTPUT)
    assert "MathTest.DISABLED_SlowMultiply" in disabled


def test_find_disabled_tests_detects_suite_level_prefix():
    disabled = find_disabled_tests(LIST_OUTPUT)
    assert "DISABLED_LegacySuite.OldCase" in disabled


def test_find_disabled_tests_excludes_enabled():
    disabled = find_disabled_tests(LIST_OUTPUT)
    assert "MathTest.Adds" not in disabled
    assert "MathTest.Subtracts" not in disabled


# ---- check_test_integrity: DISABLED_ allowlist ----


def test_check_test_integrity_passes_when_no_disabled():
    clean = "MathTest.\n  Adds\n  Subtracts\n"
    result = check_test_integrity(list_tests_output=clean, disabled_baseline=[])
    assert result["passed"] is True
    assert result["new_disabled"] == []


def test_check_test_integrity_fails_on_new_disabled_beyond_baseline():
    result = check_test_integrity(list_tests_output=LIST_OUTPUT, disabled_baseline=[])
    assert result["passed"] is False
    assert "MathTest.DISABLED_SlowMultiply" in result["new_disabled"]


def test_check_test_integrity_passes_when_disabled_in_baseline():
    baseline = ["MathTest.DISABLED_SlowMultiply", "DISABLED_LegacySuite.OldCase"]
    result = check_test_integrity(list_tests_output=LIST_OUTPUT, disabled_baseline=baseline)
    assert result["passed"] is True
    assert result["new_disabled"] == []


# ---- check_test_integrity: skipped-count baseline (GTEST_SKIP) ----

XML_TWO_SKIPPED = """<?xml version="1.0"?>
<testsuites tests="4" failures="0" disabled="0" skipped="2">
  <testsuite name="MathTest" tests="4" failures="0" skipped="2">
    <testcase name="Adds" status="run"/>
    <testcase name="Subtracts" status="run"/>
    <testcase name="A" status="run"><skipped message="GTEST_SKIP"/></testcase>
    <testcase name="B" status="run"><skipped message="GTEST_SKIP"/></testcase>
  </testsuite>
</testsuites>
"""


def test_parse_gtest_xml_skipped_counts_skipped_elements():
    assert parse_gtest_xml_skipped(XML_TWO_SKIPPED) == 2


def test_check_test_integrity_fails_when_skips_exceed_baseline():
    result = check_test_integrity(
        list_tests_output="MathTest.\n  Adds\n",
        disabled_baseline=[],
        xml_output=XML_TWO_SKIPPED,
        skipped_baseline=0,
    )
    assert result["passed"] is False
    assert result["skipped_count"] == 2


def test_check_test_integrity_passes_when_skips_within_baseline():
    result = check_test_integrity(
        list_tests_output="MathTest.\n  Adds\n",
        disabled_baseline=[],
        xml_output=XML_TWO_SKIPPED,
        skipped_baseline=2,
    )
    assert result["passed"] is True


# ---- check_disabled_tests_pass ----

XML_DISABLED_ALL_PASS = """<?xml version="1.0"?>
<testsuites tests="1" failures="0">
  <testsuite name="MathTest" tests="1" failures="0">
    <testcase name="DISABLED_SlowMultiply" status="run"/>
  </testsuite>
</testsuites>
"""

XML_DISABLED_ONE_FAILS = """<?xml version="1.0"?>
<testsuites tests="1" failures="1">
  <testsuite name="MathTest" tests="1" failures="1">
    <testcase name="DISABLED_SlowMultiply" status="run">
      <failure message="expected 6 got 5"/>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_check_disabled_tests_pass_true_when_all_pass():
    result = check_disabled_tests_pass(XML_DISABLED_ALL_PASS)
    assert result["passed"] is True
    assert result["failures"] == 0


def test_check_disabled_tests_pass_false_when_disabled_test_fails():
    result = check_disabled_tests_pass(XML_DISABLED_ONE_FAILS)
    assert result["passed"] is False
    assert result["failures"] >= 1


# ---- check_ctest_set_diff ----

CTEST_BASELINE = """\
add_test([=[MathTest.Adds]=] /build/mathtest --gtest_filter=MathTest.Adds)
add_test([=[MathTest.Subtracts]=] /build/mathtest --gtest_filter=MathTest.Subtracts)
add_test([=[MathTest.Multiplies]=] /build/mathtest --gtest_filter=MathTest.Multiplies)
"""

CTEST_DROPPED = """\
add_test([=[MathTest.Adds]=] /build/mathtest --gtest_filter=MathTest.Adds)
add_test([=[MathTest.Subtracts]=] /build/mathtest --gtest_filter=MathTest.Subtracts)
"""


def test_parse_ctest_add_tests_extracts_names():
    names = parse_ctest_add_tests(CTEST_BASELINE)
    assert "MathTest.Adds" in names
    assert "MathTest.Multiplies" in names


def test_check_ctest_set_diff_detects_removed_test():
    result = check_ctest_set_diff(CTEST_BASELINE, CTEST_DROPPED)
    assert result["passed"] is False
    assert "MathTest.Multiplies" in result["removed"]


def test_check_ctest_set_diff_passes_when_unchanged():
    result = check_ctest_set_diff(CTEST_BASELINE, CTEST_BASELINE)
    assert result["passed"] is True
    assert result["removed"] == []


def test_check_ctest_set_diff_passes_when_tests_added():
    added = CTEST_BASELINE + "add_test([=[MathTest.Divides]=] /build/mathtest --gtest_filter=MathTest.Divides)\n"
    result = check_ctest_set_diff(CTEST_BASELINE, added)
    assert result["passed"] is True
    assert result["removed"] == []
    assert "MathTest.Divides" in result["added"]


# ---- combined gate wiring ----


def test_check_test_integrity_aggregates_ctest_diff():
    result = check_test_integrity(
        list_tests_output="MathTest.\n  Adds\n",
        disabled_baseline=[],
        ctest_baseline=CTEST_BASELINE,
        ctest_current=CTEST_DROPPED,
    )
    assert result["passed"] is False
    assert "MathTest.Multiplies" in result["ctest_removed"]
