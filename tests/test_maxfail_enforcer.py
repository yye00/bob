"""Tests for pytest_snapshot.maxfail_enforcer.enforce_maxfail_zero."""

from __future__ import annotations

import pytest

from pytest_snapshot.maxfail_enforcer import enforce_maxfail_zero, MAXFAIL_ZERO


class TestBasicInjection:
    """enforce_maxfail_zero injects --maxfail=0 at the correct position."""

    def test_injects_into_bare_command(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]

    def test_injects_before_other_args(self):
        result = enforce_maxfail_zero(["pytest", "-v", "tests/"])
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"
        assert "-v" in result
        assert "tests/" in result

    def test_maxfail_zero_constant_value(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv


class TestStripsExistingMaxfail:
    """Existing --maxfail flags are stripped before --maxfail=0 is injected."""

    def test_strips_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_duplicate_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_multiple_maxfail_flags(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=3", "--maxfail=10", "tests/"])
        assert result.count("--maxfail=0") == 1
        assert "--maxfail=3" not in result
        assert "--maxfail=10" not in result


class TestBoundaryCases:
    """Boundary inputs return well-defined results without raising."""

    def test_empty_list_returns_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert result == ["--maxfail=0"]

    def test_only_maxfail_flag_returns_maxfail_zero(self):
        result = enforce_maxfail_zero(["--maxfail=99"])
        assert result == ["--maxfail=0"]

    def test_only_multiple_maxfail_flags(self):
        result = enforce_maxfail_zero(["--maxfail=1", "--maxfail=2"])
        assert result == ["--maxfail=0"]

    def test_preserves_xdist_flags(self):
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert result[1] == "--maxfail=0"
        assert "-n" in result
        assert "auto" in result

    def test_idempotent(self):
        argv = ["pytest", "--maxfail=0", "-n", "auto", "tests/"]
        result1 = enforce_maxfail_zero(argv)
        result2 = enforce_maxfail_zero(result1)
        assert result1 == result2


class TestInvalidInputRaisesValueError:
    """Invalid argv raises ValueError and does not silently succeed."""

    def test_raises_for_none(self):
        with pytest.raises(ValueError, match="list"):
            enforce_maxfail_zero(None)  # type: ignore[arg-type]

    def test_raises_for_string(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest --maxfail=0")  # type: ignore[arg-type]

    def test_raises_for_integer(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(42)  # type: ignore[arg-type]

    def test_raises_for_dict(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero({"arg": "--maxfail=0"})  # type: ignore[arg-type]

    def test_raises_for_non_string_element(self):
        with pytest.raises(ValueError, match="str"):
            enforce_maxfail_zero(["pytest", 0, "tests/"])  # type: ignore[list-item]

    def test_raises_for_none_element(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None, "tests/"])  # type: ignore[list-item]


class TestIntegration:
    """Full snapshot argv patterns that callers actually use."""

    def test_xdist_workflow(self):
        argv = ["pytest", "-n", "4", "--tb=short", "tests/unit/"]
        result = enforce_maxfail_zero(argv)
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"
        assert "-n" in result
        assert "4" in result

    def test_full_snapshot_invocation(self):
        argv = ["pytest", "--maxfail=20", "-n", "auto", "-q", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert "--maxfail=0" in result
        assert "--maxfail=20" not in result
        assert result[1] == "--maxfail=0"
