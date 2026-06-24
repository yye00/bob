"""Error path tests for bob.subagent_observability.

Feature: 406efcf3-5bce-4d23-ba99-cf96354df77a
AC: pytest: tests/test_subagent_observability_mandate_error.py —
    invalid input raises ValueError and the function does not silently
    succeed (error path)
"""

from __future__ import annotations

import pytest

from bob.subagent_observability import forbid_pytest_stdout_redirection
from bob.subagent_observability import validate_pytest_command


class TestErrorPathForbidPytestStdoutRedirection:
    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError):
            forbid_pytest_stdout_redirection(None)

    def test_none_raises_not_returns_false(self):
        """Ensure None does not silently succeed — must raise, not return (False, ...)."""
        raised = False
        try:
            forbid_pytest_stdout_redirection(None)
        except ValueError:
            raised = True
        assert raised, "None input must raise ValueError, not silently return a result"

    def test_none_raises_value_error_not_type_error(self):
        with pytest.raises(ValueError):
            forbid_pytest_stdout_redirection(None)

    def test_value_error_is_not_suppressed(self):
        """Confirm the ValueError propagates and is not caught internally."""
        exc_info = None
        try:
            forbid_pytest_stdout_redirection(None)
        except ValueError as e:
            exc_info = e
        except Exception:
            pytest.fail("Expected ValueError but got a different exception type")
        assert exc_info is not None, "ValueError must be raised for None input"

    def test_none_raises_with_informative_message(self):
        with pytest.raises(ValueError, match=r"(?i)(none|string|command|invalid)"):
            forbid_pytest_stdout_redirection(None)


class TestErrorPathValidatePytestCommandDoesNotRaiseOnInvalid:
    """validate_pytest_command accepts any string — it returns (False, reason) for bad input."""

    def test_pipe_pattern_does_not_silently_succeed(self):
        ok, msg = validate_pytest_command(
            "python -m pytest tests/ -q --tb=short 2>&1 | grep -E 'FAILED|ERROR' | head -10"
        )
        assert ok is False, "Forbidden pipe pattern must not silently succeed"
        assert msg, "Rejection message must be non-empty"

    def test_dev_null_redirect_does_not_silently_succeed(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ > /dev/null")
        assert ok is False, "Redirect to /dev/null must not silently succeed"
        assert msg, "Rejection message must be non-empty"

    def test_stderr_redirect_does_not_silently_succeed(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ 2>/dev/null")
        assert ok is False, "stderr redirect must not silently succeed"
        assert msg

    def test_quiet_flag_does_not_silently_succeed(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ -q")
        assert ok is False, "-q flag must not silently succeed"
        assert msg

    def test_no_header_flag_does_not_silently_succeed(self):
        ok, msg = validate_pytest_command("python -m pytest tests/ --no-header")
        assert ok is False, "--no-header flag must not silently succeed"
        assert msg

    def test_combined_forbidden_patterns_do_not_silently_succeed(self):
        ok, msg = validate_pytest_command(
            "python -m pytest tests/ --no-header -q 2>&1 | tail -5 > /dev/null"
        )
        assert ok is False, "Multiple forbidden patterns must not silently succeed"
        assert msg
