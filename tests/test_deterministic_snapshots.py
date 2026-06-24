"""Tests for src/pytest_snapshots.py — deterministic snapshot enforcement.

Acceptance criteria:
- File exists: src/pytest_snapshots.py
- Function defined: pytest_snapshots.enforce_maxfail_for_snapshots
- pytest: tests/test_deterministic_snapshots.py
- integration: pytest
"""

from __future__ import annotations

import pytest


class TestModuleExists:
    """The module and function must be importable."""

    def test_module_importable(self):
        import pytest_snapshots  # noqa: F401

    def test_function_exists(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        assert callable(enforce_maxfail_for_snapshots)


class TestEnforceMaxfailNoXdist:
    """Basic injection of --maxfail=0 when no xdist flags present."""

    def test_injects_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_for_snapshots(argv)
        assert result is not argv

    def test_original_args_preserved(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/", "-v"])
        assert "pytest" in result
        assert "tests/" in result
        assert "-v" in result

    def test_maxfail_zero_early_in_argv(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        idx_maxfail = result.index("--maxfail=0")
        idx_tests = result.index("tests/")
        assert idx_maxfail < idx_tests


class TestStripsExistingMaxfail:
    """Any existing --maxfail value must be stripped before injecting 0."""

    def test_strips_nonzero_maxfail(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_exactly_one_maxfail_after_strip(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=5", "tests/"])
        count = sum(1 for arg in result if arg.startswith("--maxfail"))
        assert count == 1

    def test_strips_duplicate_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(
            ["pytest", "--maxfail=0", "--maxfail=0", "tests/"]
        )
        count = sum(1 for arg in result if arg == "--maxfail=0")
        assert count == 1

    def test_strips_maxfail_without_value(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail", "tests/"])
        assert "--maxfail" not in result or result.count("--maxfail=0") == 1

    def test_strips_maxfail_equals_one(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=1"])
        assert "--maxfail=1" not in result
        assert "--maxfail=0" in result


class TestWithXdistFlags:
    """--maxfail=0 must be injected before xdist flags."""

    def test_maxfail_before_n_flag(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "4", "tests/"])
        idx_maxfail = result.index("--maxfail=0")
        idx_n = result.index("-n")
        assert idx_maxfail < idx_n

    def test_maxfail_before_numprocesses(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(
            ["pytest", "--numprocesses=auto", "tests/"]
        )
        idx_maxfail = result.index("--maxfail=0")
        idx_np = result.index("--numprocesses=auto")
        assert idx_maxfail < idx_np

    def test_xdist_flags_preserved(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "-n", "4", "tests/"])
        assert "-n" in result
        assert "4" in result

    def test_combined_xdist_and_verbose(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        argv = ["pytest", "-n", "auto", "--maxfail=10", "tests/", "-v"]
        result = enforce_maxfail_for_snapshots(argv)
        assert "--maxfail=0" in result
        assert "--maxfail=10" not in result
        assert "-n" in result
        assert "auto" in result
        assert "-v" in result


class TestEdgeCases:
    """Edge cases: empty argv, only command, injection position."""

    def test_empty_argv_returns_maxfail_zero(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots([])
        assert "--maxfail=0" in result

    def test_single_element_argv(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest"])
        assert "--maxfail=0" in result
        assert "pytest" in result

    def test_maxfail_at_index_1_when_nonempty(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_command_at_index_0_preserved(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_multiple_test_paths_preserved(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        argv = ["pytest", "tests/foo/", "tests/bar/", "-v"]
        result = enforce_maxfail_for_snapshots(argv)
        assert "tests/foo/" in result
        assert "tests/bar/" in result
        assert "--maxfail=0" in result

    def test_idempotent_on_clean_argv(self):
        from pytest_snapshots import enforce_maxfail_for_snapshots
        argv = ["pytest", "--maxfail=0", "tests/"]
        result1 = enforce_maxfail_for_snapshots(argv)
        result2 = enforce_maxfail_for_snapshots(result1)
        assert result1 == result2
