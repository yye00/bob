"""Boundary tests for pytest_plugins.snapshot_maxfail_enforcer.

Tests that empty, zero, or minimum input returns a well-defined result
rather than raising an exception.
"""

from __future__ import annotations

import pytest
from pytest_plugins import snapshot_maxfail_enforcer


class TestEmptyInput:
    """Empty list is a valid boundary input — must return a list with --maxfail=0."""

    def test_empty_list_returns_list(self):
        result = snapshot_maxfail_enforcer([])
        assert isinstance(result, list)

    def test_empty_list_contains_maxfail_zero(self):
        result = snapshot_maxfail_enforcer([])
        assert "--maxfail=0" in result

    def test_empty_list_non_empty_result(self):
        result = snapshot_maxfail_enforcer([])
        assert len(result) >= 1


class TestSingleElementInput:
    """Single-element list is the minimum non-empty input."""

    def test_single_command_returns_two_elements(self):
        result = snapshot_maxfail_enforcer(["pytest"])
        assert len(result) == 2

    def test_single_command_preserves_command(self):
        result = snapshot_maxfail_enforcer(["pytest"])
        assert result[0] == "pytest"

    def test_single_command_injects_maxfail_zero(self):
        result = snapshot_maxfail_enforcer(["pytest"])
        assert result[1] == "--maxfail=0"


class TestOnlyMaxfailInput:
    """Input consisting only of a --maxfail flag is a boundary case."""

    def test_only_maxfail_flag_returns_maxfail_zero(self):
        result = snapshot_maxfail_enforcer(["--maxfail=5"])
        assert "--maxfail=0" in result

    def test_only_maxfail_zero_returns_maxfail_zero(self):
        result = snapshot_maxfail_enforcer(["--maxfail=0"])
        assert "--maxfail=0" in result

    def test_only_maxfail_returns_list(self):
        result = snapshot_maxfail_enforcer(["--maxfail=5"])
        assert isinstance(result, list)


class TestMinimumValidArgv:
    """Two-element argv is the smallest realistic pytest command."""

    def test_two_element_argv(self):
        result = snapshot_maxfail_enforcer(["pytest", "tests/"])
        assert isinstance(result, list)
        assert "--maxfail=0" in result
        assert "pytest" in result
        assert "tests/" in result

    def test_result_is_new_object(self):
        argv = ["pytest", "tests/"]
        result = snapshot_maxfail_enforcer(argv)
        assert result is not argv

    def test_two_element_result_length(self):
        result = snapshot_maxfail_enforcer(["pytest", "tests/"])
        assert len(result) == 3  # ["pytest", "--maxfail=0", "tests/"]
