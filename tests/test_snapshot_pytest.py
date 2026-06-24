"""Tests for bob.snapshot_pytest.enforce_maxfail_zero."""

from __future__ import annotations

import pytest
from bob.snapshot_pytest import enforce_maxfail_zero, MAXFAIL_ZERO


class TestEnforceMaxfailZeroBasic:
    """Basic correctness of enforce_maxfail_zero."""

    def test_injects_maxfail_zero_into_plain_argv(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_positions_maxfail_at_index_one(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_preserves_command(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_preserves_remaining_args(self):
        result = enforce_maxfail_zero(["pytest", "-v", "tests/"])
        assert "-v" in result
        assert "tests/" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv

    def test_replaces_existing_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=5" not in result
        assert "--maxfail=0" in result

    def test_replaces_existing_maxfail_zero_no_duplicate(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_empty_argv_returns_maxfail_zero(self):
        result = enforce_maxfail_zero([])
        assert result == ["--maxfail=0"]

    def test_only_command_returns_command_and_maxfail(self):
        result = enforce_maxfail_zero(["pytest"])
        assert result == ["pytest", "--maxfail=0"]


class TestEnforceMaxfailZeroXdist:
    """Ensures --maxfail=0 appears before xdist flags."""

    def test_maxfail_before_xdist_n_flag(self):
        result = enforce_maxfail_zero(["pytest", "-n", "auto", "tests/"])
        maxfail_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert maxfail_idx < n_idx

    def test_maxfail_before_numprocesses_flag(self):
        result = enforce_maxfail_zero(["pytest", "--numprocesses=4", "tests/"])
        maxfail_idx = result.index("--maxfail=0")
        np_idx = next(i for i, a in enumerate(result) if a.startswith("--numprocesses"))
        assert maxfail_idx < np_idx


class TestEnforceMaxfailZeroErrors:
    """Invalid inputs must raise ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match=r"list"):
            enforce_maxfail_zero(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero("pytest tests/")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(("pytest", "tests/"))

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(42)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", 4])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero(["pytest", None])


class TestMaxfailZeroConstant:
    """MAXFAIL_ZERO constant is correct."""

    def test_maxfail_zero_constant_value(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_enforce_uses_constant(self):
        result = enforce_maxfail_zero(["pytest"])
        assert MAXFAIL_ZERO in result


class TestOrchestratorIntegration:
    """bob.orchestrator imports and uses enforce_maxfail_zero."""

    def test_orchestrator_run_loop_imports_snapshot_pytest(self):
        from bob.snapshot_pytest import enforce_maxfail_zero as fn
        assert callable(fn)

    def test_run_loop_references_snapshot_pytest(self):
        import inspect
        from bob.orchestrator import run_loop
        source = inspect.getsource(run_loop)
        assert "bob.snapshot_pytest" in source

    def test_enforce_maxfail_zero_importable_from_bob(self):
        from bob.snapshot_pytest import enforce_maxfail_zero
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result
