"""Tests for bob.snapshot_enforcement.enforce_maxfail_for_snapshots.

Verifies that the snapshot enforcement module correctly injects --maxfail=0
into pytest argv at the snapshot boundary, preventing non-deterministic
early-halt when pytest-xdist is active.
"""

from __future__ import annotations

import pytest

from bob.snapshot_enforcement import MAXFAIL_ZERO, enforce_maxfail_for_snapshots


class TestBasicInjection:
    """--maxfail=0 is injected into a standard pytest argv."""

    def test_injects_maxfail_zero_at_index_1(self):
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_preserves_command_at_index_0(self):
        result = enforce_maxfail_for_snapshots(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_preserves_trailing_args(self):
        result = enforce_maxfail_for_snapshots(["pytest", "tests/", "-v"])
        assert "tests/" in result
        assert "-v" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_for_snapshots(argv)
        assert result is not argv

    def test_result_is_list(self):
        result = enforce_maxfail_for_snapshots(["pytest"])
        assert isinstance(result, list)


class TestMaxfailStripping:
    """Existing --maxfail values are stripped and replaced with --maxfail=0."""

    def test_strips_nonzero_maxfail(self):
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_strips_maxfail_25(self):
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=25", "tests/"])
        assert "--maxfail=25" not in result
        assert "--maxfail=0" in result

    def test_strips_duplicate_maxfail_zero(self):
        result = enforce_maxfail_for_snapshots(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_idempotent_on_maxfail_zero(self):
        argv = ["pytest", "--maxfail=0", "tests/"]
        result = enforce_maxfail_for_snapshots(argv)
        assert result.count("--maxfail=0") == 1
        assert "--maxfail=0" in result


class TestEmptyAndMinimalInput:
    """Boundary cases: empty list and single-element list."""

    def test_empty_list_returns_maxfail_zero(self):
        result = enforce_maxfail_for_snapshots([])
        assert result == ["--maxfail=0"]

    def test_single_element_injects_at_index_1(self):
        result = enforce_maxfail_for_snapshots(["pytest"])
        assert result == ["pytest", "--maxfail=0"]

    def test_empty_list_result_is_list(self):
        result = enforce_maxfail_for_snapshots([])
        assert isinstance(result, list)


class TestXdistCompatibility:
    """--maxfail=0 appears before xdist -n flags."""

    def test_maxfail_before_n_flag(self):
        argv = ["pytest", "-n", "4", "tests/"]
        result = enforce_maxfail_for_snapshots(argv)
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert mf_idx < n_idx

    def test_maxfail_before_numprocesses(self):
        argv = ["pytest", "--numprocesses=4", "tests/"]
        result = enforce_maxfail_for_snapshots(argv)
        assert "--maxfail=0" in result
        mf_idx = result.index("--maxfail=0")
        np_idx = result.index("--numprocesses=4")
        assert mf_idx < np_idx


class TestErrorPaths:
    """Invalid argv raises ValueError; no silent failures."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match=r"list"):
            enforce_maxfail_for_snapshots(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_for_snapshots("pytest --maxfail=0")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_for_snapshots(("pytest", "tests/"))

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_for_snapshots(42)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_for_snapshots(["pytest", 4])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_for_snapshots(["pytest", None])


class TestConstants:
    """Module constants have the correct values."""

    def test_maxfail_zero_constant(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_enforce_maxfail_for_snapshots_callable(self):
        assert callable(enforce_maxfail_for_snapshots)


class TestOrchestratorIntegration:
    """bob.orchestrator can import snapshot_enforcement without error."""

    def test_snapshot_enforcement_importable_from_bob(self):
        from bob import snapshot_enforcement
        assert hasattr(snapshot_enforcement, "enforce_maxfail_for_snapshots")

    def test_orchestrator_run_loop_importable(self):
        from bob.orchestrator import run_loop
        assert hasattr(run_loop, "capture_pytest_snapshot")
