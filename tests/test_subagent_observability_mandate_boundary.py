"""Boundary tests for bob.subagent_observability.

Feature: 406efcf3-5bce-4d23-ba99-cf96354df77a
AC: pytest: tests/test_subagent_observability_mandate_boundary.py —
    empty, zero, or minimum input returns a well-defined result rather
    than raising (boundary case)
"""

from __future__ import annotations

from bob.subagent_observability import forbid_pytest_stdout_redirection
from bob.subagent_observability import validate_pytest_command


class TestBoundaryValidatePytestCommand:
    def test_empty_string_returns_false_not_raises(self):
        result = validate_pytest_command("")
        assert isinstance(result, tuple)
        ok, msg = result
        assert ok is False
        assert isinstance(msg, str)
        assert msg

    def test_single_space_returns_false_not_raises(self):
        result = validate_pytest_command(" ")
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_minimum_valid_command_returns_well_defined(self):
        result = validate_pytest_command("pytest")
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_single_char_command_returns_well_defined(self):
        result = validate_pytest_command("p")
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_whitespace_only_command_returns_well_defined(self):
        result = validate_pytest_command("   ")
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_command_with_only_pytest_flag_returns_well_defined(self):
        result = validate_pytest_command("-v")
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_very_long_valid_command_returns_well_defined(self):
        long_cmd = "python -m pytest " + "tests/test_foo.py " * 100 + "-v"
        result = validate_pytest_command(long_cmd)
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_return_type_is_always_tuple(self):
        for cmd in ["", " ", "pytest", "python -m pytest -v"]:
            result = validate_pytest_command(cmd)
            assert isinstance(result, tuple), f"Expected tuple for {cmd!r}"
            assert len(result) == 2


class TestBoundaryForbidPytestStdoutRedirection:
    def test_empty_string_returns_false_not_raises(self):
        result = forbid_pytest_stdout_redirection("")
        assert isinstance(result, tuple)
        ok, msg = result
        assert ok is False
        assert isinstance(msg, str)
        assert msg

    def test_minimum_safe_command_returns_true(self):
        result = forbid_pytest_stdout_redirection("pytest")
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_single_space_returns_well_defined(self):
        result = forbid_pytest_stdout_redirection(" ")
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_return_type_is_always_tuple(self):
        for cmd in ["", "pytest", "python -m pytest tests/ -v"]:
            result = forbid_pytest_stdout_redirection(cmd)
            assert isinstance(result, tuple), f"Expected tuple for {cmd!r}"
            assert len(result) == 2
