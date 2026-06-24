"""Tests for bob.deterministic_pytest_snapshots.

Acceptance criteria:
- File exists: src/bob/deterministic_pytest_snapshots.py
- Function defined: bob.deterministic_pytest_snapshots.enforce_maxfail_zero_snapshot
- pytest: tests/test_deterministic_pytest_snapshots.py
- integration: bob.orchestrator
"""

from __future__ import annotations

import inspect

import pytest

import bob.deterministic_pytest_snapshots as mod
from bob.deterministic_pytest_snapshots import (
    MAXFAIL_ZERO,
    enforce_maxfail_zero_snapshot,
)


class TestModuleExports:
    """Module-level export contracts."""

    def test_function_importable(self):
        assert callable(enforce_maxfail_zero_snapshot)

    def test_maxfail_zero_constant(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_module_has_maxfail_zero(self):
        assert hasattr(mod, "MAXFAIL_ZERO")
        assert mod.MAXFAIL_ZERO == "--maxfail=0"

    def test_module_docstring_mentions_xdist_or_maxfail(self):
        assert mod.__doc__ is not None
        doc = mod.__doc__.lower()
        assert "xdist" in doc or "maxfail" in doc


class TestFunctionSignature:
    """Function signature matches the spec."""

    def test_accepts_list_arg(self):
        sig = inspect.signature(enforce_maxfail_zero_snapshot)
        params = list(sig.parameters)
        assert len(params) >= 1

    def test_returns_list(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "tests/"])
        assert isinstance(result, list)


class TestMaxfailInjection:
    """--maxfail=0 is injected at the correct position."""

    def test_injects_maxfail_zero(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_maxfail_zero_at_index_one(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_command_preserved_at_index_zero(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_extra_args_preserved(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "-v", "tests/"])
        assert "-v" in result
        assert "tests/" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero_snapshot(argv)
        assert result is not argv

    def test_result_length(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "tests/"])
        assert len(result) == 3  # ["pytest", "--maxfail=0", "tests/"]


class TestMaxfailReplacement:
    """Existing --maxfail flags are replaced, not duplicated."""

    def test_replaces_nonzero_maxfail(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=0" in result
        assert "--maxfail=5" not in result

    def test_no_duplicate_maxfail_zero(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_maxfail_equals_form_replaced(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "--maxfail=100"])
        assert "--maxfail=0" in result
        assert "--maxfail=100" not in result


class TestXdistOrdering:
    """--maxfail=0 appears before xdist -n flags."""

    def test_maxfail_before_n_flag(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "-n", "4", "tests/"])
        maxfail_idx = result.index("--maxfail=0")
        n_idx = result.index("-n")
        assert maxfail_idx < n_idx

    def test_xdist_flags_preserved(self):
        result = enforce_maxfail_zero_snapshot(["pytest", "-n", "4", "tests/"])
        assert "-n" in result
        assert "4" in result


class TestEmptyArgv:
    """Empty argv returns a list with --maxfail=0."""

    def test_empty_returns_list(self):
        result = enforce_maxfail_zero_snapshot([])
        assert isinstance(result, list)

    def test_empty_contains_maxfail_zero(self):
        result = enforce_maxfail_zero_snapshot([])
        assert "--maxfail=0" in result


class TestInvalidInputRaisesValueError:
    """Invalid input raises ValueError."""

    def test_none_raises(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero_snapshot(None)  # type: ignore[arg-type]

    def test_string_raises(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero_snapshot("pytest")  # type: ignore[arg-type]

    def test_non_string_element_raises(self):
        with pytest.raises(ValueError):
            enforce_maxfail_zero_snapshot(["pytest", 42])  # type: ignore[list-item]


class TestOrchestratorIntegration:
    """bob.deterministic_pytest_snapshots integrates with bob.orchestrator."""

    def test_orchestrator_run_loop_imports_correctly(self):
        from bob.orchestrator import run_loop
        assert hasattr(run_loop, "capture_pytest_snapshot")

    def test_module_importable_from_orchestrator_import_chain(self):
        from bob.deterministic_pytest_snapshots import enforce_maxfail_zero_snapshot
        assert callable(enforce_maxfail_zero_snapshot)

    def test_enforce_maxfail_zero_snapshot_used_by_orchestrator(self):
        import ast
        import pathlib
        run_loop_path = pathlib.Path(__file__).parent.parent / "src" / "bob" / "orchestrator" / "run_loop.py"
        source = run_loop_path.read_text()
        assert "deterministic_pytest_snapshots" in source
        assert "enforce_maxfail_zero_snapshot" in source
