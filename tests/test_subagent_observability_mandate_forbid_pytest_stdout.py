"""Tests for bob.subagent_observability_mandate_forbid_pytest_stdout.

Feature: 5c8a28ea-42e3-47d9-bb56-8f1e4a8234c6
AC: pytest: tests/test_subagent_observability_mandate_forbid_pytest_stdout.py::test_subagent_observability_mandate_forbid_pytest_stdout
"""

from __future__ import annotations

import pytest

from bob.subagent_observability_mandate_forbid_pytest_stdout import (
    subagent_observability_mandate_forbid_pytest_stdout,
)


def test_subagent_observability_mandate_forbid_pytest_stdout():
    """Core AC test: function exists, returns (False, reason) for forbidden patterns."""
    # Exact pattern from the incident report
    ok, reason = subagent_observability_mandate_forbid_pytest_stdout(
        "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
    )
    assert ok is False
    assert reason


class TestForbiddenRedirects:
    def test_stdout_to_dev_null_rejected(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ > /dev/null"
        )
        assert ok is False
        assert msg

    def test_stderr_to_dev_null_rejected(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ 2>/dev/null"
        )
        assert ok is False
        assert msg

    def test_pipe_to_grep_rejected(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ 2>&1 | grep -E 'FAILED|ERROR'"
        )
        assert ok is False
        assert msg

    def test_pipe_to_head_rejected(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ | head -10"
        )
        assert ok is False
        assert msg

    def test_quiet_flag_rejected(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ -q"
        )
        assert ok is False
        assert msg

    def test_no_header_flag_rejected(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ --no-header"
        )
        assert ok is False
        assert msg


class TestSafeInvocations:
    def test_clean_verbose_invocation_passes(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/test_foo.py -v"
        )
        assert ok is True
        assert msg == ""

    def test_verbose_with_tb_short_passes(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/test_foo.py -v --tb=short"
        )
        assert ok is True
        assert msg == ""

    def test_specific_test_function_passes(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/test_foo.py::test_bar -v"
        )
        assert ok is True
        assert msg == ""


class TestReturnType:
    def test_returns_tuple_of_bool_and_str(self):
        result = subagent_observability_mandate_forbid_pytest_stdout(
            "python -m pytest tests/ -v"
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_empty_command_returns_false(self):
        ok, msg = subagent_observability_mandate_forbid_pytest_stdout("")
        assert ok is False
        assert msg
