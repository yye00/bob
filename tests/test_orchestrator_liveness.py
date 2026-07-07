"""Tests for bob.orchestrator_liveness (feature 788eabf2).

Feature: orchestrator-liveness probe MUST match ``bob[0-9]+`` regex AND honor
``.bob.lock`` holder PID. The prior operator/watchdog used ``pgrep bob run``,
which missed a running ``bobN run --all`` process (e.g. bob14), false-stalled,
removed a legitimately-held ``.bob.lock``, and raced a second orchestrator on
the same DB.

Contract:
  - is_orchestrator_running() returns True when any process matching
    ``bob[0-9]+ run`` (or the legacy ``bob run``) is alive.
  - should_remove_lock(lock_path, db_path=None) returns True ONLY when ALL
    three signals agree no orchestrator is alive:
      1. no matching pgrep process
      2. the ``.bob.lock`` holder PID is not alive (kill -0)
      3. the DB has no ``executing`` rows updated within the last 60 s
"""

from __future__ import annotations

import os

import pytest

from bob.orchestrator_liveness import is_orchestrator_running, should_remove_lock


# ---------------------------------------------------------------------------
# is_orchestrator_running — signal #1 (regex process match)
# ---------------------------------------------------------------------------

class TestIsOrchestratorRunning:
    def test_returns_bool(self):
        with _patch_pids([]):
            result = is_orchestrator_running()
        assert type(result) is bool

    def test_no_processes_returns_false(self):
        with _patch_pids([]):
            assert is_orchestrator_running() is False

    def test_legacy_bob_run_matches(self):
        """The legacy ``bob run`` form (no generation digit) still matches."""
        with _patch_pids([(99001, "bob run --all")]):
            assert is_orchestrator_running() is True

    def test_gen_n_alias_matches(self):
        """The gen-N binary alias ``bob14 run`` matches — the core defect fix."""
        with _patch_pids([(99002, "bob14 run --all")]):
            assert is_orchestrator_running() is True

    def test_full_path_gen_n_alias_matches(self):
        with _patch_pids([(99003, "/home/u/.venv/bin/bob59 run --all")]):
            assert is_orchestrator_running() is True

    def test_own_pid_excluded(self):
        with _patch_pids([(os.getpid(), "bob14 run --all")]):
            assert is_orchestrator_running() is False

    def test_shell_wrapper_excluded(self):
        with _patch_pids([(99004, "bash -c 'bob17 run --all'")]):
            assert is_orchestrator_running() is False

    def test_non_matching_process_returns_false(self):
        with _patch_pids([(99005, "python3 -m http.server")]):
            assert is_orchestrator_running() is False


# ---------------------------------------------------------------------------
# should_remove_lock — three-signal gate
# ---------------------------------------------------------------------------

class TestShouldRemoveLock:
    def test_returns_bool(self, tmp_path):
        lock = tmp_path / ".bob.lock"
        lock.write_text("0\n", encoding="utf-8")
        with _patch_pids([]), _patch_db(False):
            assert type(should_remove_lock(lock)) is bool

    def test_all_signals_clear_allows_removal(self, tmp_path):
        """When no process, dead lock PID, and no executing rows → True."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("0\n", encoding="utf-8")  # PID 0 → not alive
        with _patch_pids([]), _patch_db(False):
            assert should_remove_lock(lock) is True

    def test_process_alive_blocks_removal(self, tmp_path):
        lock = tmp_path / ".bob.lock"
        lock.write_text("0\n", encoding="utf-8")
        with _patch_pids([(99010, "bob14 run --all")]), _patch_db(False):
            assert should_remove_lock(lock) is False

    def test_live_lock_holder_blocks_removal(self, tmp_path):
        """A lock file naming the current (live) PID blocks removal."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        with _patch_pids([]), _patch_db(False):
            assert should_remove_lock(lock) is False

    def test_recent_executing_rows_block_removal(self, tmp_path):
        lock = tmp_path / ".bob.lock"
        lock.write_text("0\n", encoding="utf-8")
        with _patch_pids([]), _patch_db(True):
            assert should_remove_lock(lock) is False

    def test_db_error_is_conservative_blocks_removal(self, tmp_path):
        lock = tmp_path / ".bob.lock"
        lock.write_text("0\n", encoding="utf-8")
        with _patch_pids([]), _patch_db_raises():
            assert should_remove_lock(lock) is False

    def test_missing_lock_file_still_gated_by_process(self, tmp_path):
        """A missing lock file (dead holder) does not by itself allow removal
        when a matching process is alive."""
        missing = tmp_path / "nope.lock"
        with _patch_pids([(99011, "bob59 run")]), _patch_db(False):
            assert should_remove_lock(missing) is False


# ---------------------------------------------------------------------------
# Integration with bob.orchestrator
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_orchestrator_package_importable(self):
        import bob.orchestrator  # noqa: F401

    def test_module_reexports_are_callable(self):
        import bob.orchestrator_liveness as mod
        assert callable(mod.is_orchestrator_running)
        assert callable(mod.should_remove_lock)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

from unittest.mock import patch


def _patch_pids(pairs):
    return patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=list(pairs),
    )


def _patch_db(has_rows: bool):
    return patch(
        "bob.orchestrator.liveness_probe._has_recent_executing_rows",
        return_value=has_rows,
    )


def _patch_db_raises():
    return patch(
        "bob.orchestrator.liveness_probe._has_recent_executing_rows",
        side_effect=RuntimeError("DB unavailable"),
    )
