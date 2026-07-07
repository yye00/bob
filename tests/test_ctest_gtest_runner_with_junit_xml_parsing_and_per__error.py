"""Error-path tests for bob.verification.ctest_runner.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.verification.ctest_runner import (
    parse_junit_xml,
    run_ctest_ac,
    build_ctest_command,
)


def test_parse_junit_xml_rejects_non_string():
    with pytest.raises(ValueError):
        parse_junit_xml(None)


def test_parse_junit_xml_rejects_empty_string():
    with pytest.raises(ValueError):
        parse_junit_xml("   ")


def test_parse_junit_xml_rejects_malformed_xml():
    with pytest.raises(ValueError):
        parse_junit_xml("<testsuite><testcase></testsuite>")  # unclosed tag


def test_run_ctest_ac_rejects_empty_criterion(tmp_path):
    with pytest.raises(ValueError):
        run_ctest_ac(criterion="   ", build_dir=str(tmp_path),
                     junit_xml="<testsuite/>")


def test_run_ctest_ac_rejects_none_build_dir():
    with pytest.raises(ValueError):
        run_ctest_ac(criterion="ctest: x", build_dir=None,
                     junit_xml="<testsuite/>")


def test_build_ctest_command_rejects_empty_regex():
    with pytest.raises(ValueError):
        build_ctest_command(build_dir="/tmp/b", regex="", junit_out="/tmp/o.xml")


def test_build_ctest_command_rejects_none_build_dir():
    with pytest.raises(ValueError):
        build_ctest_command(build_dir=None, regex="x", junit_out="/tmp/o.xml")
