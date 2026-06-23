"""Tests for bob3.subagent_observability.validate_pytest_command and forbid_pytest_stdout_redirection.

Feature: 1f6399ab-8d95-4c94-86ac-c4fd65698a92
AC: pytest: tests/test_subagent_observability.py
"""

from __future__ import annotations

import pytest

from bob3.subagent_observability import forbid_pytest_stdout_redirection
from bob3.subagent_observability import validate_pytest_command


class TestValidatePytestCommandAllowsCleanInvocations:
    def test_simple_verbose_invocation_passes(self):
        ok, _ = validate_pytest_command("python -m pytest tests/test_foo.py -v")
        assert ok is True

    def test_verbose_directory_invocation_passes(self):
        ok, _ = validate_pytest_command("python -m pytest tests/ -v")
        assert ok is True

    def test_verbose_with_extra_flags_passes(self):
        ok, _ = validate_pytest_command("python -m pytest tests/test_foo.py -v --tb=short")
        assert ok is True

    def test_empty_string_returns_false(self):
        ok, msg = validate_pytest_command("")
        assert ok is False
        assert msg


class TestValidatePytestCommandRejectsRedirection:
    def test_stdout_to_dev_null_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ > /dev/null")
        assert ok is False
        assert msg

    def test_stderr_to_dev_null_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ 2>/dev/null")
        assert ok is False
        assert msg

    def test_combined_redirect_to_dev_null_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ 2>&1 > /dev/null")
        assert ok is False
        assert msg

    def test_pipe_to_grep_rejected(self):
        ok, msg = validate_pytest_command(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR'"
        )
        assert ok is False
        assert msg

    def test_pipe_to_head_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ | head -10")
        assert ok is False
        assert msg

    def test_pipe_to_tail_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ | tail -20")
        assert ok is False
        assert msg

    def test_pipe_to_grep_then_head_rejected(self):
        ok, msg = validate_pytest_command(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
        )
        assert ok is False
        assert msg


class TestValidatePytestCommandRejectsQuietModes:
    def test_dash_q_flag_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ -q")
        assert ok is False
        assert msg

    def test_no_header_flag_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ --no-header")
        assert ok is False
        assert msg

    def test_dash_q_with_other_flags_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ -q --tb=short")
        assert ok is False
        assert msg

    def test_no_header_with_dash_q_rejected(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ --no-header -q")
        assert ok is False
        assert msg


class TestValidatePytestCommandErrorMessages:
    def test_pipe_rejection_mentions_pipe(self):
        _, msg = validate_pytest_command("python -m pytest tests/ | grep FAILED")
        assert "pipe" in msg.lower() or "|" in msg

    def test_dev_null_rejection_mentions_redirect(self):
        _, msg = validate_pytest_command("python -m pytest tests/ > /dev/null")
        assert "redirect" in msg.lower() or "/dev/null" in msg

    def test_quiet_rejection_mentions_quiet(self):
        _, msg = validate_pytest_command("python -m pytest tests/ -q")
        assert "quiet" in msg.lower() or "-q" in msg

    def test_no_header_rejection_mentions_suppression(self):
        _, msg = validate_pytest_command("python -m pytest tests/ --no-header")
        assert "suppress" in msg.lower() or "--no-header" in msg or "output" in msg.lower()


class TestValidatePytestCommandReturnType:
    def test_returns_tuple_of_bool_and_str(self):
        result = validate_pytest_command("python -m pytest tests/ -v")
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_valid_command_returns_empty_message(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ -v")
        assert ok is True
        assert msg == ""

    def test_invalid_command_returns_non_empty_message(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ -q")
        assert ok is False
        assert len(msg) > 0


class TestForbidPytestStdoutRedirection:
    def test_safe_command_returns_true(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/test_foo.py -v")
        assert ok is True
        assert msg == ""

    def test_empty_string_returns_false_not_crash(self):
        ok, msg = forbid_pytest_stdout_redirection("")
        assert ok is False
        assert msg

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            forbid_pytest_stdout_redirection(None)

    def test_pipe_to_grep_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
        )
        assert ok is False
        assert msg

    def test_dev_null_redirect_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ > /dev/null")
        assert ok is False
        assert msg

    def test_quiet_flag_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ -q")
        assert ok is False
        assert msg

    def test_returns_tuple_of_bool_and_str(self):
        result = forbid_pytest_stdout_redirection("python -m pytest tests/test_foo.py -v")
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)
