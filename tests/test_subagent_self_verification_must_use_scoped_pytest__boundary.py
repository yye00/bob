"""Boundary tests for get_scoped_pytest_command in bob.superpowers.

Feature: 40799127-8e65-4c47-b671-0bbc6aa9ce66
AC: pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__boundary.py

Tests that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case).
"""

from __future__ import annotations

import pytest

from bob.superpowers import get_scoped_pytest_command


class TestGetScopedPytestCommandBoundary:
    """Boundary cases: empty/None/minimum input must not raise."""

    def test_none_input_returns_string(self):
        """None acceptance_criteria returns a well-defined string (no raise)."""
        result = get_scoped_pytest_command(None)
        assert isinstance(result, str)

    def test_empty_list_returns_string(self):
        """Empty list returns a well-defined string (no raise)."""
        result = get_scoped_pytest_command([])
        assert isinstance(result, str)

    def test_empty_list_falls_back_to_full_suite(self):
        """Empty list falls back to 'python -m pytest tests/ -v'."""
        result = get_scoped_pytest_command([])
        assert result == "python -m pytest tests/ -v"

    def test_none_falls_back_to_full_suite(self):
        """None falls back to 'python -m pytest tests/ -v'."""
        result = get_scoped_pytest_command(None)
        assert result == "python -m pytest tests/ -v"

    def test_single_pytest_ac_returns_scoped_command(self):
        """Single pytest: AC returns scoped command (minimum useful input)."""
        acs = ["pytest: tests/test_foo.py"]
        result = get_scoped_pytest_command(acs)
        assert result == "python -m pytest tests/test_foo.py -v"

    def test_list_with_no_pytest_acs_returns_full_suite(self):
        """List with ACs but no pytest: prefix returns full-suite fallback."""
        acs = ["File exists: src/bob/foo.py", "Function defined: foo.bar"]
        result = get_scoped_pytest_command(acs)
        assert result == "python -m pytest tests/ -v"

    def test_single_empty_string_in_list_returns_full_suite(self):
        """List with a single empty string returns fallback (no raise)."""
        result = get_scoped_pytest_command([""])
        assert isinstance(result, str)
        assert result == "python -m pytest tests/ -v"

    def test_pytest_ac_with_empty_path_skipped(self):
        """pytest: AC with empty path is skipped; falls back to full suite."""
        acs = ["pytest: "]
        result = get_scoped_pytest_command(acs)
        assert result == "python -m pytest tests/ -v"

    def test_result_always_starts_with_python_m_pytest(self):
        """Result always starts with 'python -m pytest' for all boundary inputs."""
        for acs in [None, [], [""], ["File exists: x"], ["pytest: tests/test_x.py"]]:
            result = get_scoped_pytest_command(acs)
            assert result.startswith("python -m pytest"), (
                f"Expected 'python -m pytest' prefix for input {acs!r}, got {result!r}"
            )

    def test_result_always_ends_with_v_flag(self):
        """Result always ends with '-v' for all boundary inputs."""
        for acs in [None, [], [""], ["File exists: x"], ["pytest: tests/test_x.py"]]:
            result = get_scoped_pytest_command(acs)
            assert result.endswith(" -v"), (
                f"Expected '-v' suffix for input {acs!r}, got {result!r}"
            )
