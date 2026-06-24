"""Tests for bob.subagent_observability_mandate.

Feature: 55010d1c-e1cc-412b-9dff-f1cf355cd9a5
AC: pytest: tests/test_subagent_observability_mandate.py
"""

from __future__ import annotations

import pytest

from bob.subagent_observability_mandate import forbid_pytest_stdout_redirection
from bob.subagent_observability_mandate import validate_pytest_command
from bob.subagent_observability_mandate import validate_pytest_output_streaming


class TestForbidPytestStdoutRedirection:
    def test_pipe_to_grep_rejected(self):
        """Exact incident command from the bug report must be rejected."""
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

    def test_pipe_to_head_rejected(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/ | head -10")
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

    def test_safe_verbose_invocation_accepted(self):
        ok, msg = forbid_pytest_stdout_redirection("python -m pytest tests/test_foo.py -v")
        assert ok is True
        assert msg == ""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            forbid_pytest_stdout_redirection(None)

    def test_returns_tuple(self):
        result = forbid_pytest_stdout_redirection("python -m pytest tests/ -v")
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestValidatePytestOutputStreaming:
    def test_safe_verbose_invocation_accepted(self):
        ok, msg = validate_pytest_output_streaming("python -m pytest tests/test_foo.py -v")
        assert ok is True
        assert msg == ""

    def test_pipe_to_grep_rejected(self):
        ok, msg = validate_pytest_output_streaming(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
        )
        assert ok is False
        assert msg

    def test_stdout_to_dev_null_rejected(self):
        ok, msg = validate_pytest_output_streaming("python -m pytest tests/ > /dev/null")
        assert ok is False
        assert msg

    def test_quiet_flag_rejected(self):
        ok, msg = validate_pytest_output_streaming("python -m pytest tests/ -q")
        assert ok is False
        assert msg

    def test_no_header_rejected(self):
        ok, msg = validate_pytest_output_streaming("python -m pytest tests/ --no-header")
        assert ok is False
        assert msg

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_pytest_output_streaming(None)

    def test_returns_tuple(self):
        result = validate_pytest_output_streaming("python -m pytest tests/ -v")
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestModuleExports:
    def test_forbid_pytest_stdout_redirection_is_callable(self):
        assert callable(forbid_pytest_stdout_redirection)

    def test_validate_pytest_command_is_callable(self):
        assert callable(validate_pytest_command)

    def test_validate_pytest_output_streaming_is_callable(self):
        assert callable(validate_pytest_output_streaming)


class TestIntegrationWithSuperpowers:
    def test_superpowers_exports_forbid_function(self):
        from bob import superpowers
        assert hasattr(superpowers, "forbid_pytest_stdout_redirection")
        assert callable(superpowers.forbid_pytest_stdout_redirection)

    def test_mandate_and_superpowers_agree_on_forbidden_command(self):
        from bob import superpowers as sp
        cmd = "python -m pytest tests/ -q --tb=short 2>&1 | grep FAILED | head -10"
        mandate_ok, _ = forbid_pytest_stdout_redirection(cmd)
        superpowers_ok, _ = sp.forbid_pytest_stdout_redirection(cmd)
        assert mandate_ok is False
        assert superpowers_ok is False

    def test_mandate_and_superpowers_agree_on_safe_command(self):
        from bob import superpowers as sp
        cmd = "python -m pytest tests/test_foo.py -v"
        mandate_ok, _ = forbid_pytest_stdout_redirection(cmd)
        superpowers_ok, _ = sp.forbid_pytest_stdout_redirection(cmd)
        assert mandate_ok is True
        assert superpowers_ok is True
