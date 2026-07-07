"""Boundary tests — empty/zero/minimum input returns a well-defined result.

The gate must not raise on empty-but-valid inputs; an empty test list, empty
baselines, and empty ctest files are legitimate boundary cases.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bob.cpp_test_integrity_gate import (
    check_ctest_set_diff,
    check_disabled_tests_pass,
    check_test_integrity,
    find_disabled_tests,
    parse_ctest_add_tests,
    parse_gtest_list_tests,
    parse_gtest_xml_skipped,
)


def test_empty_list_tests_output_returns_no_names():
    assert parse_gtest_list_tests("") == []


def test_empty_list_tests_output_finds_no_disabled():
    assert find_disabled_tests("") == []


def test_check_test_integrity_empty_output_passes():
    result = check_test_integrity(list_tests_output="", disabled_baseline=[])
    assert result["passed"] is True
    assert result["new_disabled"] == []


def test_parse_gtest_xml_skipped_empty_returns_zero():
    assert parse_gtest_xml_skipped("") == 0


def test_check_disabled_tests_pass_empty_xml_is_wellformed():
    """No disabled tests to run means nothing failed — a passing, well-defined result."""
    result = check_disabled_tests_pass("")
    assert result["passed"] is True
    assert result["failures"] == 0


def test_check_ctest_set_diff_both_empty_passes():
    result = check_ctest_set_diff("", "")
    assert result["passed"] is True
    assert result["removed"] == []
    assert result["added"] == []


def test_parse_ctest_add_tests_empty_returns_empty():
    assert parse_ctest_add_tests("") == []


def test_check_test_integrity_all_optional_omitted_passes():
    """Minimal invocation — only the required list output and baseline."""
    result = check_test_integrity(
        list_tests_output="Suite.\n  OnlyCase\n", disabled_baseline=[]
    )
    assert result["passed"] is True


def test_zero_skipped_baseline_with_zero_skips_passes():
    xml = '<?xml version="1.0"?><testsuites tests="0" skipped="0"></testsuites>'
    result = check_test_integrity(
        list_tests_output="",
        disabled_baseline=[],
        xml_output=xml,
        skipped_baseline=0,
    )
    assert result["passed"] is True
    assert result["skipped_count"] == 0
