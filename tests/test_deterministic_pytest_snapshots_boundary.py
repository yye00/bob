"""Boundary tests for bob.deterministic_pytest_snapshots.

Empty, zero, or minimum input returns a well-defined result rather than
raising an exception.
"""

from __future__ import annotations

import pytest

from bob.deterministic_pytest_snapshots import (
    build_snapshot_pytest_args,
    enforce_maxfail_zero,
)


class TestEnforceEmptyInput:
    """Empty list is a valid boundary input — returns a list with --maxfail=0."""

    def test_empty_list_returns_list(self):
        result = enforce_maxfail_zero([])
        assert isinstance(result, list)

    def test_empty_list_contains_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert "--maxfail=0" in result

    def test_empty_list_non_empty_result(self):
        result = enforce_maxfail_zero([])
        assert len(result) >= 1


class TestEnforceSingleElementInput:
    """Single-element list is the minimum non-empty input."""

    def test_single_command_returns_two_elements(self):
        result = enforce_maxfail_zero(["pytest"])
        assert len(result) == 2

    def test_single_command_preserves_command(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result[0] == "pytest"

    def test_single_command_injects_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result[1] == "--maxfail=0"


class TestEnforceOnlyMaxfailInput:
    """Input consisting only of a --maxfail flag is a boundary case."""

    def test_only_maxfail_flag_returns_maxfail_zero(self):
        result = enforce_maxfail_zero(["--maxfail=5"])
        assert "--maxfail=0" in result

    def test_only_maxfail_zero_returns_maxfail_zero(self):
        result = enforce_maxfail_zero(["--maxfail=0"])
        assert "--maxfail=0" in result
        assert result.count("--maxfail=0") == 1

    def test_only_maxfail_returns_list(self):
        result = enforce_maxfail_zero(["--maxfail=5"])
        assert isinstance(result, list)


class TestBuildEmptyInput:
    """build_snapshot_pytest_args handles empty argv."""

    def test_empty_list_returns_list(self):
        result = build_snapshot_pytest_args([])
        assert isinstance(result, list)
        assert "--maxfail=0" in result

    def test_empty_list_with_numprocesses(self):
        result = build_snapshot_pytest_args([], numprocesses=2)
        assert "--maxfail=0" in result
        assert "-n" in result
        assert result.index("--maxfail=0") < result.index("-n")

    def test_numprocesses_none_is_default(self):
        # None numprocesses is the minimum/default xdist input — no -n added.
        result = build_snapshot_pytest_args(["pytest"], numprocesses=None)
        assert "-n" not in result


class TestBuildMinimumValidArgv:
    """Two-element argv is the smallest realistic pytest command."""

    def test_two_element_argv(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"])
        assert isinstance(result, list)
        assert "--maxfail=0" in result
        assert "pytest" in result
        assert "tests/" in result

    def test_result_is_new_object(self):
        argv = ["pytest", "tests/"]
        result = build_snapshot_pytest_args(argv)
        assert result is not argv

    def test_two_element_result_length(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"])
        assert len(result) == 3

    def test_numprocesses_zero_boundary(self):
        # Zero workers is a valid minimum xdist value, not an error.
        result = build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=0)
        assert "-n" in result
        assert "0" in result
