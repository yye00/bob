"""Tests for bob.pytest_snapshots.enforce_maxfail_zero.

Verifies that the snapshot boundary enforcer correctly injects --maxfail=0
and strips any existing --maxfail flag from pytest argv, guaranteeing
deterministic before/after snapshots even when pytest-xdist is active.
"""

from __future__ import annotations

import pytest

from bob.pytest_snapshots import MAXFAIL_ZERO, enforce_maxfail_zero


class TestEnforceMaxfailZero:
    """Core contract: --maxfail=0 is always injected at position 1."""

    def test_injects_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_position_after_command(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"

    def test_preserves_other_args(self):
        result = enforce_maxfail_zero(["pytest", "-v", "tests/"])
        assert "-v" in result
        assert "tests/" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_maxfail_zero_constant(self):
        assert MAXFAIL_ZERO == "--maxfail=0"


class TestStripsExistingMaxfail:
    """Existing --maxfail values must be replaced by --maxfail=0."""

    def test_replaces_maxfail_nonzero(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=0" in result
        assert "--maxfail=5" not in result

    def test_replaces_maxfail_one(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=1"])
        assert "--maxfail=0" in result
        assert "--maxfail=1" not in result

    def test_idempotent_when_already_maxfail_zero(self):
        argv = ["pytest", "--maxfail=0", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result.count("--maxfail=0") == 1

    def test_strips_bare_maxfail_flag(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail", "tests/"])
        assert "--maxfail" not in result or "--maxfail=0" in result

    def test_multiple_maxfail_flags_reduced_to_one(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "--maxfail=10"])
        assert result.count("--maxfail=0") == 1


class TestBoundaryInputs:
    """Edge cases at the boundaries of valid input."""

    def test_empty_list_returns_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert "--maxfail=0" in result
        assert isinstance(result, list)

    def test_single_command_positions_maxfail_at_one(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]

    def test_xdist_flags_preserved(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert "-n" in result
        assert "4" in result
        assert "--maxfail=0" in result

    def test_maxfail_zero_before_xdist_flag(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4"])
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx


class TestInvalidInputRaises:
    """Invalid argv must raise ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest tests/")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 42])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])
