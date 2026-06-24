"""Boundary tests for orchestrator-liveness probe ancestry/shell-wrapper exclusions.

AC: pytest: tests/test_orchestrator_liveness_probe_must_exclude_process_a_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising.

Covers boundary cases for:
  - bob3.orchestrator.probe_ancestry.is_self_or_ancestor
  - bob3.orchestrator.probe_ancestry.is_shell_wrapper
  - bob3.orchestrator.probe_ancestry.collect_ancestor_pids
  - bob3.orchestrator_liveness_probe_must_exclude_process_ancestry (probe function)
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from bob3.orchestrator.probe_ancestry import (
    collect_ancestor_pids,
    is_self_or_ancestor,
    is_shell_wrapper,
)
import bob3.orchestrator_liveness_probe_must_exclude_process_ancestry as _mod

_probe = _mod.orchestrator_liveness_probe_must_exclude_process_ancestry


# ---------------------------------------------------------------------------
# is_shell_wrapper boundary cases
# ---------------------------------------------------------------------------

class TestIsShellWrapperBoundary:
    """is_shell_wrapper: boundary inputs return well-defined False, not raise."""

    def test_empty_string_returns_false(self):
        """Empty cmdline returns False (no argv[0] to inspect)."""
        result = is_shell_wrapper("")
        assert result is False

    def test_whitespace_only_returns_false(self):
        """Whitespace-only cmdline returns False."""
        result = is_shell_wrapper("   ")
        assert result is False

    def test_single_space_returns_false(self):
        """Single space cmdline returns False without raising."""
        result = is_shell_wrapper(" ")
        assert result is False

    def test_single_non_shell_char_returns_false(self):
        """Single non-shell character is not a shell wrapper."""
        result = is_shell_wrapper("x")
        assert result is False

    def test_returns_bool_not_truthy(self):
        """Return type is exactly bool, not a truthy/falsy non-bool."""
        assert type(is_shell_wrapper("")) is bool
        assert type(is_shell_wrapper("bash")) is bool


# ---------------------------------------------------------------------------
# is_self_or_ancestor boundary cases
# ---------------------------------------------------------------------------

class TestIsSelfOrAncestorBoundary:
    """is_self_or_ancestor: boundary PID values return well-defined results."""

    def test_pid_zero_returns_false(self):
        """PID 0 is never a real process; must not raise, returns False."""
        result = is_self_or_ancestor(0)
        assert result is False

    def test_pid_one_returns_false(self):
        """PID 1 (init/systemd) is not our ancestor in test environments."""
        result = is_self_or_ancestor(1)
        assert result is False

    def test_own_pid_returns_true(self):
        """Minimum meaningful input: own PID must return True."""
        result = is_self_or_ancestor(os.getpid())
        assert result is True

    def test_returns_bool_type(self):
        """Return value is exactly bool."""
        result = is_self_or_ancestor(os.getpid())
        assert type(result) is bool

    def test_large_pid_not_in_ancestry_returns_false(self):
        """Very large PID unlikely to be in ancestry returns False without raising."""
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({os.getpid()}),
        ):
            result = is_self_or_ancestor(2 ** 22 - 1)
        assert result is False


# ---------------------------------------------------------------------------
# collect_ancestor_pids boundary cases
# ---------------------------------------------------------------------------

class TestCollectAncestorPidsBoundary:
    """collect_ancestor_pids: boundary PID values return well-defined frozensets."""

    def test_pid_one_returns_frozenset_with_one(self):
        """PID 1 (init) walk terminates immediately; {1} returned."""
        result = collect_ancestor_pids(1)
        assert 1 in result
        assert isinstance(result, frozenset)

    def test_pid_zero_returns_frozenset(self):
        """PID 0 does not raise; returns a frozenset."""
        result = collect_ancestor_pids(0)
        assert isinstance(result, frozenset)

    def test_returns_frozenset_for_own_pid(self):
        """Minimum live PID (os.getpid()) returns a frozenset."""
        result = collect_ancestor_pids(os.getpid())
        assert isinstance(result, frozenset)
        assert len(result) >= 1

    def test_unreadable_proc_does_not_raise(self):
        """collect_ancestor_pids never raises even when /proc is unavailable."""
        def _raise(path, *args, **kwargs):
            raise OSError("proc unreadable")

        with patch("builtins.open", _raise):
            result = collect_ancestor_pids(99999)
        assert isinstance(result, frozenset)
        assert 99999 in result


# ---------------------------------------------------------------------------
# Probe function boundary cases
# ---------------------------------------------------------------------------

class TestProbeFunctionBoundary:
    """The AC-mandated probe function handles boundary process lists gracefully."""

    def test_empty_process_list_returns_false(self):
        """Zero candidates → probe returns False (not raises)."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            result = _probe()
        assert result is False
        assert type(result) is bool

    def test_single_pid_1_skipped_returns_false(self):
        """PID=1 (init) is always skipped; returns False."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(1, "bob3 run --all")],
        ):
            result = _probe()
        assert result is False

    def test_empty_cmdline_candidate_returns_false(self):
        """Candidate with empty cmdline is skipped; returns False."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(99999, "")],
        ):
            result = _probe()
        assert result is False

    def test_returns_bool_type(self):
        """Return type is always exactly bool."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            result = _probe()
        assert type(result) is bool
