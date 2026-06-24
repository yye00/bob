"""Tests for bob.snapshot_runner.enforce_maxfail_zero.

Covers the core contract: --maxfail=0 is always injected at position 1
(or 0 for empty input), existing --maxfail flags are stripped, and invalid
input raises ValueError.
"""

from __future__ import annotations

import pytest
from bob.snapshot_runner import enforce_maxfail_zero, MAXFAIL_ZERO


class TestEnforceMaxfailZeroHappyPath:
    """enforce_maxfail_zero returns a new list with --maxfail=0 at position 1."""

    def test_basic_argv_gets_maxfail_injected(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result == ["pytest", "--maxfail=0", "tests/"]

    def test_existing_maxfail_is_stripped(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=25", "tests/"])
        assert "--maxfail=25" not in result
        assert "--maxfail=0" in result

    def test_existing_maxfail_zero_not_duplicated(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_returns_new_list_not_same_object(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_maxfail_zero_at_index_one(self):
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert result[1] == "--maxfail=0"

    def test_other_flags_preserved_after_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "-v", "--tb=short", "tests/"])
        assert "-v" in result
        assert "--tb=short" in result

    def test_xdist_n_flag_preserved_after_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result
        assert result.index("--maxfail=0") < result.index("-n")

    def test_maxfail_zero_constant(self):
        assert MAXFAIL_ZERO == "--maxfail=0"


class TestEnforceMaxfailZeroBoundary:
    """Boundary cases: empty list and single-element list."""

    def test_empty_list_returns_list_with_maxfail(self):
        result = enforce_maxfail_zero([])
        assert result == ["--maxfail=0"]

    def test_single_element_injects_at_index_one(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]

    def test_only_maxfail_flag_replaced(self):
        result = enforce_maxfail_zero(["--maxfail=99"])
        assert result == ["--maxfail=0"]


class TestEnforceMaxfailZeroErrorPaths:
    """Invalid argv raises ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="list"):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest --maxfail=0 tests/")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_int_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 4])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])

    def test_bool_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", True])
