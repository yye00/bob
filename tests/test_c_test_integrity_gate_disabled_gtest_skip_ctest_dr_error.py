"""Error-path tests — invalid input raises ValueError, no silent success."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bob.cpp_test_integrity_gate import (
    check_ctest_set_diff,
    check_disabled_tests_pass,
    check_test_integrity,
    parse_gtest_list_tests,
    parse_gtest_xml_skipped,
)


def test_list_tests_output_none_raises():
    with pytest.raises((ValueError, TypeError)):
        parse_gtest_list_tests(None)  # type: ignore[arg-type]


def test_list_tests_output_non_str_raises():
    with pytest.raises((ValueError, TypeError)):
        parse_gtest_list_tests(123)  # type: ignore[arg-type]


def test_check_test_integrity_none_output_raises():
    with pytest.raises((ValueError, TypeError)):
        check_test_integrity(list_tests_output=None, disabled_baseline=[])  # type: ignore[arg-type]


def test_check_test_integrity_baseline_non_list_raises():
    with pytest.raises((ValueError, TypeError)):
        check_test_integrity(
            list_tests_output="Suite.\n  Case\n",
            disabled_baseline="not-a-list",  # type: ignore[arg-type]
        )


def test_check_test_integrity_negative_skipped_baseline_raises():
    with pytest.raises(ValueError):
        check_test_integrity(
            list_tests_output="",
            disabled_baseline=[],
            xml_output="<testsuites skipped='0'/>",
            skipped_baseline=-1,
        )


def test_parse_gtest_xml_malformed_raises():
    with pytest.raises(ValueError):
        parse_gtest_xml_skipped("<not-valid-xml <<<")


def test_check_disabled_tests_pass_malformed_xml_raises():
    with pytest.raises(ValueError):
        check_disabled_tests_pass("<<< broken xml")


def test_check_disabled_tests_pass_none_raises():
    with pytest.raises((ValueError, TypeError)):
        check_disabled_tests_pass(None)  # type: ignore[arg-type]


def test_check_ctest_set_diff_none_baseline_raises():
    with pytest.raises((ValueError, TypeError)):
        check_ctest_set_diff(None, "")  # type: ignore[arg-type]


def test_check_ctest_set_diff_none_current_raises():
    with pytest.raises((ValueError, TypeError)):
        check_ctest_set_diff("", None)  # type: ignore[arg-type]
