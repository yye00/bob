"""Tests for pytest_snapshots.enforce_maxfail_zero — xdist snapshot determinism.

Acceptance criteria:
- File exists: src/pytest_snapshots.py
- Function defined: pytest_snapshots.enforce_maxfail_zero
- pytest: tests/test_snapshots_xdist.py
- integration: pytest
"""

from __future__ import annotations

import pytest


class TestModuleAndFunctionExist:
    """The module and enforce_maxfail_zero must be importable and callable."""

    def test_module_importable(self):
        import pytest_snapshots  # noqa: F401

    def test_enforce_maxfail_zero_exists(self):
        from pytest_snapshots import enforce_maxfail_zero
        assert callable(enforce_maxfail_zero)


class TestEnforceMaxfailZeroBasic:
    """enforce_maxfail_zero injects --maxfail=0 into argv."""

    def test_injects_maxfail_zero_no_xdist(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list_not_same_object(self):
        from pytest_snapshots import enforce_maxfail_zero
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_maxfail_zero_precedes_test_path(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result.index("--maxfail=0") < result.index("tests/")

    def test_empty_argv_returns_maxfail_only(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero([])
        assert result == ["--maxfail=0"]


class TestEnforceMaxfailZeroStripsExisting:
    """Any existing --maxfail value is stripped before injecting 0."""

    def test_strips_nonzero_maxfail(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_one(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=1", "tests/"])
        assert "--maxfail=1" not in result
        assert "--maxfail=0" in result

    def test_strips_duplicate_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_strips_bare_maxfail_flag(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail", "tests/"])
        assert "--maxfail" not in result
        assert "--maxfail=0" in result


class TestEnforceMaxfailZeroWithXdist:
    """enforce_maxfail_zero works correctly when xdist flags are present."""

    def test_injects_before_xdist_n_auto(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "--maxfail=0" in result
        assert result.index("--maxfail=0") < result.index("-n")

    def test_injects_before_xdist_n_4(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert "--maxfail=0" in result
        assert result.index("--maxfail=0") < result.index("-n")

    def test_injects_before_numprocesses(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--numprocesses=8", "tests/"])
        assert "--maxfail=0" in result
        assert result.index("--maxfail=0") < result.index("--numprocesses=8")

    def test_strips_nonzero_maxfail_with_xdist(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=10", "-n", "auto", "tests/"])
        assert "--maxfail=10" not in result
        assert "--maxfail=0" in result

    def test_idempotent_when_already_maxfail_zero_and_xdist(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "-n", "auto", "tests/"])
        assert result.count("--maxfail=0") == 1
        assert "--maxfail=0" in result

    def test_xdist_flags_preserved_in_output(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        assert "-n" in result
        assert "auto" in result


class TestEnforceMaxfailZeroEdgeCases:
    """Edge cases for enforce_maxfail_zero."""

    def test_single_element_argv(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest"])
        assert "--maxfail=0" in result
        assert result[0] == "pytest"
        assert result[1] == "--maxfail=0"

    def test_exactly_one_maxfail_zero_in_result(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/", "-v"])
        assert result.count("--maxfail=0") == 1

    def test_maxfail_zero_at_index_one_when_nonempty(self):
        from pytest_snapshots import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_complex_argv_with_multiple_flags(self):
        from pytest_snapshots import enforce_maxfail_zero
        argv = ["pytest", "-v", "--tb=short", "-n", "4", "--maxfail=3", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert "--maxfail=0" in result
        assert "--maxfail=3" not in result
        assert result.count("--maxfail=0") == 1
        assert "-v" in result
        assert "--tb=short" in result
        assert "-n" in result
        assert "tests/" in result
