"""Tests for bob.deterministic_pytest_snapshots.

Acceptance criteria:
- File exists: src/bob/deterministic_pytest_snapshots.py
- Function defined: bob.deterministic_pytest_snapshots.build_snapshot_pytest_args
- Function defined: bob.deterministic_pytest_snapshots.enforce_maxfail_zero
- pytest: tests/test_deterministic_pytest_snapshots.py
- integration: bob.snapshot
"""

from __future__ import annotations

import inspect

import pytest

import bob.deterministic_pytest_snapshots as mod
from bob.deterministic_pytest_snapshots import (
    MAXFAIL_ZERO,
    build_snapshot_pytest_args,
    enforce_maxfail_zero,
)


class TestModuleExports:
    """Module-level export contracts."""

    def test_enforce_maxfail_zero_importable(self):
        assert callable(enforce_maxfail_zero)

    def test_build_snapshot_pytest_args_importable(self):
        assert callable(build_snapshot_pytest_args)

    def test_maxfail_zero_constant(self):
        assert MAXFAIL_ZERO == "--maxfail=0"

    def test_module_has_maxfail_zero(self):
        assert hasattr(mod, "MAXFAIL_ZERO")
        assert mod.MAXFAIL_ZERO == "--maxfail=0"

    def test_module_docstring_mentions_xdist_or_maxfail(self):
        assert mod.__doc__ is not None
        doc = mod.__doc__.lower()
        assert "xdist" in doc or "maxfail" in doc

    def test_all_exports(self):
        assert "enforce_maxfail_zero" in mod.__all__
        assert "build_snapshot_pytest_args" in mod.__all__


class TestIntegrationBobSnapshot:
    """integration: bob.snapshot — module imports the shared snapshot module."""

    def test_bob_snapshot_imported(self):
        import bob.snapshot

        assert mod._snapshot is bob.snapshot

    def test_bob_snapshot_shares_maxfail_constant(self):
        import bob.snapshot

        assert bob.snapshot.MAXFAIL_ZERO == mod.MAXFAIL_ZERO


class TestFunctionSignatures:
    """Signatures match the spec."""

    def test_enforce_accepts_one_positional(self):
        sig = inspect.signature(enforce_maxfail_zero)
        assert len(sig.parameters) >= 1

    def test_build_accepts_argv_and_numprocesses(self):
        sig = inspect.signature(build_snapshot_pytest_args)
        params = sig.parameters
        assert "argv" in params
        assert "numprocesses" in params
        assert params["numprocesses"].default is None


class TestEnforceMaxfailInjection:
    """enforce_maxfail_zero injects --maxfail=0 at the correct position."""

    def test_injects_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_maxfail_zero_at_index_one(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_command_preserved_at_index_zero(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert result[0] == "pytest"

    def test_extra_args_preserved(self):
        result = enforce_maxfail_zero(["pytest", "-v", "tests/"])
        assert "-v" in result
        assert "tests/" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = enforce_maxfail_zero(argv)
        assert result is not argv
        assert argv == ["pytest", "tests/"]  # input not mutated

    def test_result_length(self):
        result = enforce_maxfail_zero(["pytest", "tests/"])
        assert len(result) == 3


class TestEnforceMaxfailReplacement:
    """Existing --maxfail flags are replaced, not duplicated."""

    def test_replaces_nonzero_maxfail(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=5", "tests/"])
        assert "--maxfail=0" in result
        assert "--maxfail=5" not in result

    def test_no_duplicate_maxfail_zero(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=0", "tests/"])
        assert result.count("--maxfail=0") == 1

    def test_maxfail_equals_form_replaced(self):
        result = enforce_maxfail_zero(["pytest", "--maxfail=100"])
        assert "--maxfail=0" in result
        assert "--maxfail=100" not in result


class TestEnforceXdistOrdering:
    """--maxfail=0 appears before xdist -n flags."""

    def test_maxfail_before_n_flag(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert result.index("--maxfail=0") < result.index("-n")

    def test_xdist_flags_preserved(self):
        result = enforce_maxfail_zero(["pytest", "-n", "4", "tests/"])
        assert "-n" in result
        assert "4" in result


class TestBuildSnapshotPytestArgs:
    """build_snapshot_pytest_args composes maxfail enforcement + xdist."""

    def test_enforces_maxfail_zero(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"])
        assert "--maxfail=0" in result

    def test_returns_new_list(self):
        argv = ["pytest", "tests/"]
        result = build_snapshot_pytest_args(argv)
        assert result is not argv
        assert argv == ["pytest", "tests/"]

    def test_maxfail_at_index_one(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"])
        assert result[1] == "--maxfail=0"

    def test_appends_numprocesses(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=4)
        assert "-n" in result
        assert "4" in result

    def test_numprocesses_after_maxfail(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=4)
        assert result.index("--maxfail=0") < result.index("-n")

    def test_no_numprocesses_no_n_flag(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"])
        assert "-n" not in result

    def test_existing_n_flag_not_duplicated(self):
        result = build_snapshot_pytest_args(
            ["pytest", "-n", "8", "tests/"], numprocesses=4
        )
        # caller-supplied -n 8 wins; no second -n appended
        assert result.count("-n") == 1
        assert "8" in result
        assert "4" not in result

    def test_numprocesses_zero_appends(self):
        result = build_snapshot_pytest_args(["pytest", "tests/"], numprocesses=0)
        assert "-n" in result
        assert "0" in result

    def test_replaces_maxfail_and_adds_xdist(self):
        result = build_snapshot_pytest_args(
            ["pytest", "--maxfail=3", "tests/"], numprocesses=2
        )
        assert "--maxfail=3" not in result
        assert result.count("--maxfail=0") == 1
        assert result.index("--maxfail=0") < result.index("-n")
