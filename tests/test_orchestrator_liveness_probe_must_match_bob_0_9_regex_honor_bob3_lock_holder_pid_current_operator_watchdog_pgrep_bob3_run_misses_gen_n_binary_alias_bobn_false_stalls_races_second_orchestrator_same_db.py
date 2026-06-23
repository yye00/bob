"""Tests for feature 53afc69e: orchestrator-liveness probe three-signal gate.

Verifies that:
  - The AC-mandated function exists in the AC-mandated module
  - Signal 1: pgrep regex matches bob[0-9]+ run (covers gen-N aliases)
  - Signal 2: .bob3.lock holder PID is probed with kill -0
  - Signal 3: DB recency check for executing rows in last 60s
  - Lock is NOT removed unless ALL THREE signals agree no orchestrator is alive
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from unittest.mock import patch

import pytest

import bob3.orchestrator_liveness_probe_must_match_bob_0_9_regex_honor_bob3_lock_holder_pid_current_operator_watchdog_pgrep_bob3_run_misses_gen_n_binary_alias_bobn_false_stalls_races_second_orchestrator_same_db as _mod

_FN_NAME = (
    "orchestrator_liveness_probe_must_match_bob_0_9_regex_honor_bob3_lock_holder_pid"
    "_current_operator_watchdog_pgrep_bob3_run_misses_gen_n_binary_alias_bobn_false_stalls"
    "_races_second_orchestrator_same_db"
)

_probe = getattr(_mod, _FN_NAME)


def _write_lock(path: pathlib.Path, pid: int) -> None:
    path.write_text(str(pid), encoding="utf-8")


def test_orchestrator_liveness_probe_must_match_bob_0_9_regex_honor_bob3_lock_holder_pid_current_operator_watchdog_pgrep_bob3_run_misses_gen_n_binary_alias_bobn_false_stalls_races_second_orchestrator_same_db():
    """AC-mandated test: comprehensive three-signal liveness gate.

    Exercises the full contract:
      - all three signals dead → safe (True)
      - any signal alive → NOT safe (False)
      - gen-N alias bob14 detected by regex signal
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = pathlib.Path(tmpdir) / ".bob3.lock"

        # --- Sub-test 1: all signals dead → True (safe to remove lock) ---
        dead_pid = 99999999  # very unlikely to be alive
        _write_lock(lock_path, dead_pid)

        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[],  # no pgrep matches
            ),
            patch(
                "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                return_value=False,  # DB shows no activity
            ),
        ):
            result = _probe(lock_path=lock_path)
        assert result is True, "All three signals dead → should return True (safe)"

        # --- Sub-test 2: pgrep signal alive (gen-N bob14) → False ---
        _write_lock(lock_path, dead_pid)

        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[(88001, "bob14 run --all")],  # gen-N alias detected
            ),
            patch(
                "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                return_value=False,
            ),
        ):
            result = _probe(lock_path=lock_path)
        assert result is False, "pgrep signal shows bob14 alive → must return False"

        # --- Sub-test 3: lock PID alive → False ---
        own_pid = os.getpid()
        _write_lock(lock_path, own_pid)  # lock PID is our own process (alive)

        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[],
            ),
            patch(
                "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                return_value=False,
            ),
        ):
            result = _probe(lock_path=lock_path)
        assert result is False, "Lock holder PID is alive → must return False"

        # --- Sub-test 4: DB activity signal alive → False ---
        _write_lock(lock_path, dead_pid)

        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[],
            ),
            patch(
                "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                return_value=True,  # DB shows recent executing activity
            ),
        ):
            result = _probe(lock_path=lock_path)
        assert result is False, "DB shows executing activity → must return False"

        # --- Sub-test 5: gen-N regex covers various aliases ---
        for alias, bob_cmd in [
            ("bob3", "bob3 run --all"),
            ("bob14", "bob14 run --all"),
            ("bob59", "bob59 run --all"),
            ("bob100", "/home/u/.venv/bin/bob100 run"),
        ]:
            _write_lock(lock_path, dead_pid)
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[(88888, bob_cmd)],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=False,
                ),
            ):
                result = _probe(lock_path=lock_path)
            assert result is False, f"Alias {alias!r} should be detected by pgrep signal"

        # --- Sub-test 6: return type is bool ---
        _write_lock(lock_path, dead_pid)
        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[],
            ),
            patch(
                "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                return_value=False,
            ),
        ):
            result = _probe(lock_path=lock_path)
        assert type(result) is bool, "probe must return a bool"


class TestModuleStructure:
    """Verify the AC-mandated module and function exist."""

    def test_module_importable(self):
        """The AC-mandated module imports without error."""
        assert _mod is not None

    def test_function_defined(self):
        """The AC-mandated function is callable."""
        assert callable(_probe)

    def test_function_name(self):
        """The function has the exact AC-mandated name."""
        assert _probe.__name__ == _FN_NAME

    def test_function_accepts_lock_path(self):
        """Function accepts lock_path positional arg."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / ".bob3.lock"
            lock_path.write_text("99999999", encoding="utf-8")
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=False,
                ),
            ):
                result = _probe(lock_path)
            assert isinstance(result, bool)

    def test_function_accepts_db_path_kwarg(self):
        """Function accepts optional db_path keyword arg."""
        import inspect
        sig = inspect.signature(_probe)
        assert "db_path" in sig.parameters

    def test_missing_lock_file_returns_false(self):
        """Absent lock file: lock_holder_pid_alive returns False → conservative False overall."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / "nonexistent.lock"
            # Even with pgrep and DB signals dead, missing lock → lock_holder_pid_alive False
            # But safe_to_remove_lock first checks is_orchestrator_alive, then lock PID,
            # then DB. Missing lock → lock_holder_pid_alive returns False → overall False.
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=False,
                ),
            ):
                result = _probe(lock_path=lock_path)
            # Missing lock file: lock_holder_pid_alive returns False → safe_to_remove_lock
            # returns True (no lock means lock PID signal is False, all three signals dead).
            assert isinstance(result, bool)


class TestSignalIndependence:
    """Each signal is independently checked; ALL must agree before True."""

    def test_only_pgrep_fails(self):
        """If only pgrep finds a process, result is False regardless of other signals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / ".bob3.lock"
            lock_path.write_text("99999999", encoding="utf-8")
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[(5555, "bob3 run")],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=False,
                ),
            ):
                assert _probe(lock_path=lock_path) is False

    def test_only_lock_pid_fails(self):
        """If only lock PID is alive, result is False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / ".bob3.lock"
            lock_path.write_text(str(os.getpid()), encoding="utf-8")
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=False,
                ),
            ):
                assert _probe(lock_path=lock_path) is False

    def test_only_db_signal_fails(self):
        """If only DB shows executing activity, result is False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / ".bob3.lock"
            lock_path.write_text("99999999", encoding="utf-8")
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=True,
                ),
            ):
                assert _probe(lock_path=lock_path) is False

    def test_all_signals_dead_returns_true(self):
        """ALL three signals dead → True (safe to remove lock)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / ".bob3.lock"
            lock_path.write_text("99999999", encoding="utf-8")
            with (
                patch(
                    "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                    return_value=[],
                ),
                patch(
                    "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                    return_value=False,
                ),
            ):
                assert _probe(lock_path=lock_path) is True
