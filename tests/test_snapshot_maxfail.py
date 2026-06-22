"""Tests for pytest_snapshot_maxfail.enforce_maxfail_zero."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pytest_snapshot_maxfail import enforce_maxfail_zero, MAXFAIL_ZERO


class TestEnforceMaxfailZeroBasic:
    """Basic injection and stripping behavior."""

    def test_injects_maxfail_zero_into_bare_command(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]

    def test_injects_maxfail_zero_before_other_args(self):
        result = enforce_maxfail_zero(["pytest", "-v", "tests/"])
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"
        assert "-v" in result
        assert "tests/" in result

    def test_strips_existing_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_existing_maxfail_zero_then_reinjects(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_duplicate_maxfail_flags(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=3", "--maxfail=10", "tests/"])
        assert result.count("--maxfail=0") == 1
        assert "--maxfail=3" not in result
        assert "--maxfail=10" not in result

    def test_preserves_xdist_flags_after_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert result[1] == "--maxfail=0"
        assert "-n" in result
        assert "auto" in result

    def test_maxfail_zero_constant_is_correct_string(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_returns_new_list_not_same_object(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv


class TestEnforceMaxfailZeroBoundaryCases:
    """Boundary cases: empty and zero-element inputs."""

    def test_empty_list_returns_maxfail_zero(self):
        """Boundary: empty argv must not crash, must return a well-defined result."""
        result = enforce_maxfail_zero([])
        assert result == ["--maxfail=0"]

    def test_list_with_only_maxfail_flag_returns_maxfail_zero(self):
        """When argv contains only a --maxfail flag, result is still [--maxfail=0]."""
        result = enforce_maxfail_zero(["--maxfail=99"])
        assert result == ["--maxfail=0"]

    def test_list_with_multiple_maxfail_flags_only(self):
        result = enforce_maxfail_zero(["--maxfail=1", "--maxfail=2"])
        assert result == ["--maxfail=0"]

    def test_single_element_non_maxfail(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"

    def test_maxfail_equals_zero_form_is_stripped_and_reinject(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0"])
        # exactly one --maxfail=0, no duplicates
        assert result == ["pytest", "--maxfail=0"]


class TestEnforceMaxfailZeroInvalidInput:
    """Invalid input must raise ValueError, not silently succeed."""

    def test_raises_value_error_for_none(self):
        with pytest.raises(ValueError, match="list"):
            enforce_maxfail_zero(None)  # type: ignore[arg-type]

    def test_raises_value_error_for_string(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest --maxfail=0")  # type: ignore[arg-type]

    def test_raises_value_error_for_integer(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(42)  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_element(self):
        with pytest.raises(ValueError, match="str"):
            enforce_maxfail_zero(["pytest", 0, "tests/"])  # type: ignore[list-item]

    def test_raises_value_error_for_none_element(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None, "tests/"])  # type: ignore[list-item]

    def test_raises_value_error_for_dict(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero({"arg": "--maxfail=0"})  # type: ignore[arg-type]

    def test_raises_value_error_for_list_of_ints(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero([1, 2, 3])  # type: ignore[list-item]


class TestEnforceMaxfailZeroIntegration:
    """Integration: result is always a valid pytest argv with --maxfail=0 at position 1."""

    def test_xdist_workflow_injects_before_n(self):
        argv = ["pytest", "-n", "4", "--tb=short", "tests/unit/"]
        result = enforce_maxfail_zero(argv)
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"
        assert "-n" in result
        assert "4" in result

    def test_full_snapshot_invocation_pattern(self):
        argv = ["pytest", "--maxfail=20", "-n", "auto", "-q", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert "--maxfail=0" in result
        assert "--maxfail=20" not in result
        assert result[1] == "--maxfail=0"

    def test_idempotent_when_already_correct(self):
        argv = ["pytest", "--maxfail=0", "-n", "auto", "tests/"]
        result1 = enforce_maxfail_zero(argv)
        result2 = enforce_maxfail_zero(result1)
        assert result1 == result2
