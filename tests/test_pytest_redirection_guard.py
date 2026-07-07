"""Tests for bob.pytest_redirection_guard.

Feature: dcd82948-4cd1-4865-a6d9-693c22b0ebb1
AC: pytest: tests/test_pytest_redirection_guard.py
    File exists: src/bob/pytest_redirection_guard.py
    Function defined: bob.pytest_redirection_guard.forbid_pytest_stdout_redirection
"""

from __future__ import annotations

import pytest

from bob.pytest_redirection_guard import forbid_pytest_stdout_redirection


class TestForbiddenPatterns:
    def test_incident_command_rejected(self):
        """The exact incident command must be rejected."""
        ok, reason = forbid_pytest_stdout_redirection(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
        )
        assert ok is False
        assert reason

    def test_stdout_to_dev_null_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ > /dev/null")
        assert ok is False
        assert msg

    def test_stderr_to_dev_null_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ 2>/dev/null")
        assert ok is False
        assert msg

    def test_pipe_to_grep_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ | grep FAILED")
        assert ok is False
        assert msg

    def test_pipe_to_head_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ | head -10")
        assert ok is False
        assert msg

    def test_pipe_to_tail_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ | tail -5")
        assert ok is False
        assert msg

    def test_quiet_flag_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ -q")
        assert ok is False
        assert msg

    def test_no_header_flag_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ --no-header")
        assert ok is False
        assert msg


class TestSafeCommands:
    def test_verbose_streaming_command_allowed(self):
        ok, msg = forbid_pytest_stdout_redirection(
            "python -m pytest tests/test_foo.py -v"
        )
        assert ok is True
        assert msg == ""

    def test_plain_pytest_allowed(self):
        ok, msg = forbid_pytest_stdout_redirection("pytest")
        assert ok is True
        assert msg == ""

    def test_scoped_verbose_command_allowed(self):
        ok, msg = forbid_pytest_stdout_redirection(
            "python -m pytest tests/my_feature/ -v"
        )
        assert ok is True


class TestReturnContract:
    def test_returns_two_tuple(self):
        result = forbid_pytest_stdout_redirection("pytest -v")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_ok_is_bool_msg_is_str(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ | grep X")
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestErrorPath:
    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            forbid_pytest_stdout_redirection(None)

    def test_none_does_not_silently_succeed(self):
        raised = False
        try:
            forbid_pytest_stdout_redirection(None)
        except ValueError:
            raised = True
        assert raised


class TestBoundary:
    def test_empty_string_returns_false(self):
        ok, msg = forbid_pytest_stdout_redirection("")
        assert ok is False
        assert msg
