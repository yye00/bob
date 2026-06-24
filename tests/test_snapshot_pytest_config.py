"""Tests for bob3.snapshot_pytest_config.enforce_maxfail_zero."""

from __future__ import annotations

import pytest
from bob3.snapshot_pytest_config import enforce_maxfail_zero, MAXFAIL_ZERO


class TestEnforceMaxfailZeroBasic:
    """Core behaviour: --maxfail=0 is always present at index 1."""

    def test_returns_list(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert isinstance(result, list)

    def test_injects_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_maxfail_zero_at_index_one(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_command_preserved_at_index_zero(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_other_args_preserved(self):
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert "tests/" in result
        assert "-v" in result

    def test_result_is_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv


class TestEnforceMaxfailZeroStripsExisting:
    """Existing --maxfail flags are replaced with --maxfail=0."""

    def test_strips_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_existing_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_bare_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail", "tests/"])
        assert "--maxfail" not in [a for a in result if a != "--maxfail=0"]

    def test_strips_multiple_maxfail_flags(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=1", "--maxfail=2", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_maxfail_zero_at_index_one_after_strip(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=99", "tests/", "-v"])
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"


class TestEnforceMaxfailZeroEmptyAndMinimal:
    """Edge cases: empty list and single-element list."""

    def test_empty_list_returns_list(self):
        result = enforce_maxfail_zero([])
        assert isinstance(result, list)

    def test_empty_list_contains_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert "--maxfail=0" in result

    def test_single_command_preserves_command(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result[0] == "pytest"

    def test_single_command_injects_maxfail_at_index_one(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result[1] == "--maxfail=0"


class TestEnforceMaxfailZeroXdistSafety:
    """--maxfail=0 is placed before any xdist -n flags."""

    def test_maxfail_zero_before_xdist_n(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        maxfail_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert maxfail_idx < n_idx

    def test_xdist_args_preserved(self):
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result


class TestEnforceMaxfailZeroErrors:
    """Invalid input raises ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest tests/")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_integer_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 4])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])

    def test_error_message_mentions_list(self):
        with pytest.raises(ValueError, match=r"list"):
            enforce_maxfail_zero(None)


class TestMaxfailZeroConstant:
    """MAXFAIL_ZERO constant is the canonical flag string."""

    def test_constant_value(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_constant_injected_by_function(self):
        result = enforce_maxfail_zero(["pytest"])
        assert MAXFAIL_ZERO in result
