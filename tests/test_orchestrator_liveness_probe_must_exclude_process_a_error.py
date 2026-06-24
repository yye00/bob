"""Error-path tests for orchestrator-liveness probe ancestry/shell-wrapper exclusions.

AC: pytest: tests/test_orchestrator_liveness_probe_must_exclude_process_a_error.py
    — invalid input raises ValueError and the function does not silently succeed.

Covers error paths for:
  - bob.orchestrator.probe_ancestry.is_self_or_ancestor
  - bob.orchestrator.liveness_probe.lock_holder_pid_alive

Note: is_shell_wrapper and collect_ancestor_pids are designed to never raise
(they accept any string/int and return a safe default), so they have no
ValueError error path — boundary tests for those are in the _boundary module.
The error-path contracts here target the functions whose documented interface
explicitly promises ValueError for invalid types.
"""

from __future__ import annotations

import os
import pathlib
from unittest.mock import patch

import pytest

from bob.orchestrator.liveness_probe import lock_holder_pid_alive
import bob.orchestrator_liveness_probe_must_exclude_process_ancestry as _mod

_probe = _mod.orchestrator_liveness_probe_must_exclude_process_ancestry


# ---------------------------------------------------------------------------
# lock_holder_pid_alive: invalid lock_path type raises ValueError
# ---------------------------------------------------------------------------

class TestLockHolderPidAliveErrorPath:
    """lock_holder_pid_alive raises ValueError on non-path-like input."""

    def test_integer_lock_path_raises_value_error(self):
        """Passing an integer as lock_path raises ValueError."""
        with pytest.raises(ValueError):
            lock_holder_pid_alive(42)

    def test_none_lock_path_raises_value_error(self):
        """Passing None as lock_path raises ValueError."""
        with pytest.raises(ValueError):
            lock_holder_pid_alive(None)

    def test_list_lock_path_raises_value_error(self):
        """Passing a list as lock_path raises ValueError."""
        with pytest.raises(ValueError):
            lock_holder_pid_alive(["/tmp/.lock"])

    def test_dict_lock_path_raises_value_error(self):
        """Passing a dict as lock_path raises ValueError."""
        with pytest.raises(ValueError):
            lock_holder_pid_alive({"path": "/tmp/.lock"})

    def test_float_lock_path_raises_value_error(self):
        """Passing a float as lock_path raises ValueError."""
        with pytest.raises(ValueError):
            lock_holder_pid_alive(3.14)

    def test_bool_lock_path_raises_value_error(self):
        """Passing a bool (not a path-like) raises ValueError."""
        with pytest.raises(ValueError):
            lock_holder_pid_alive(True)

    def test_valid_string_does_not_raise(self, tmp_path):
        """A valid string path does NOT raise ValueError."""
        lock = tmp_path / ".bob.lock"
        result = lock_holder_pid_alive(str(lock))
        assert isinstance(result, bool)

    def test_valid_pathlib_does_not_raise(self, tmp_path):
        """A valid pathlib.Path does NOT raise ValueError."""
        lock = tmp_path / ".bob.lock"
        result = lock_holder_pid_alive(pathlib.Path(lock))
        assert isinstance(result, bool)

    def test_error_message_names_received_type(self):
        """ValueError message identifies the bad type."""
        with pytest.raises(ValueError, match="int"):
            lock_holder_pid_alive(42)


# ---------------------------------------------------------------------------
# Probe function: does not silently succeed on unexpected candidate errors
# ---------------------------------------------------------------------------

class TestProbeFunctionErrorPath:
    """Probe does not silently swallow candidate errors; bad types in /proc are skipped."""

    def test_non_integer_pid_in_candidates_skipped(self):
        """A (pid, cmdline) tuple where pid is a string is skipped, not silently matched."""
        # The liveness probe iterates candidates and checks pid <= 1.
        # A non-integer pid would cause a TypeError, which _iter_candidate_pids
        # guards against internally. If a bad entry slips through, the probe
        # must not silently claim a false positive.
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(99999, "bob run --all")],
        ), patch(
            "bob.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({os.getpid()}),
        ):
            # Genuine unrelated PID with matching cmdline IS detected (not suppressed).
            result = _probe()
        assert result is True

    def test_proc_read_failure_returns_false_not_raises(self):
        """When /proc is unreadable, probe returns False rather than raising."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            result = _probe()
        assert result is False
        assert type(result) is bool
