"""Aggregate liveness probe tests (AC: pytest: tests/test_liveness_probe.py).

Verifies the AC-mandated public API:
  - bob.liveness.probe_matches_orchestrator
  - bob.liveness.check_lock_file_holder
  - bob.liveness.verify_db_activity
  - bob.liveness.check_orchestrator_running
  - bob.liveness.validate_lock_file_holder
  - Integration with bob.orchestrator via bob.orchestrator.liveness_probe

This module tests the bob.liveness public wrapper layer and the
three-signal gate (check_orchestrator_running + validate_lock_file_holder +
_has_recent_executing_rows must ALL be dead before safe_to_remove_lock=True).
"""

from __future__ import annotations

import os
import pathlib
from unittest.mock import patch

import pytest

from bob.liveness import (
    check_orchestrator_running,
    validate_lock_file_holder,
    verify_lock_file_holder,
    safe_to_remove_lock,
    probe_matches_orchestrator,
    check_lock_file_holder,
    verify_db_activity,
)


# ---------------------------------------------------------------------------
# check_orchestrator_running tests (AC: bob.liveness.check_orchestrator_running)
# ---------------------------------------------------------------------------

class TestCheckOrchestratorRunning:
    """Tests for check_orchestrator_running (wraps is_orchestrator_alive)."""

    def test_returns_true_for_bob14_run(self):
        """Detects 'bob14 run --all' as a live orchestrator process."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_001, "bob14 run --all")],
        ):
            assert check_orchestrator_running() is True

    def test_returns_true_for_bob_run(self):
        """Detects legacy 'bob run' process."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_002, "bob run --all")],
        ):
            assert check_orchestrator_running() is True

    def test_returns_true_for_any_generation(self):
        """Matches bob[0-9]+ for gen 1 through 99+."""
        for gen in [1, 3, 14, 15, 59, 100]:
            with patch(
                "bob.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[(999_003, f"bob{gen} run --all")],
            ):
                assert check_orchestrator_running() is True, f"Expected True for bob{gen}"

    def test_returns_true_for_full_path_binary(self):
        """Detects '/home/user/.venv/bin/bob59 run --all'."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_004, "/home/user/.venv/bin/bob59 run --all")],
        ):
            assert check_orchestrator_running() is True

    def test_returns_false_when_no_matching_process(self):
        """Returns False when no bob[0-9]+ run process exists."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_005, "python some_script.py")],
        ):
            assert check_orchestrator_running() is False

    def test_returns_false_for_empty_process_list(self):
        """Returns False on empty process list."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            assert check_orchestrator_running() is False

    def test_returns_false_for_bob_without_run(self):
        """'bob14 status' is not an orchestrator."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_006, "bob14 status")],
        ):
            assert check_orchestrator_running() is False

    def test_excludes_own_pid(self):
        """Does not count the current process as an external orchestrator."""
        own_pid = os.getpid()
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(own_pid, "bob14 run --all")],
        ):
            assert check_orchestrator_running() is False

    def test_excludes_shell_wrapper(self):
        """A bash parent quoting 'bob17 run' is not counted."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_007, "bash -c 'bob17 run --all'")],
        ):
            assert check_orchestrator_running() is False

    def test_does_not_match_bare_bob(self):
        """'bob run --all' (no digit suffix) must not match."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(999_008, "bob run --all")],
        ):
            assert check_orchestrator_running() is False


# ---------------------------------------------------------------------------
# validate_lock_file_holder tests (AC: bob.liveness.validate_lock_file_holder)
# ---------------------------------------------------------------------------

class TestValidateLockFileHolder:
    """Tests for validate_lock_file_holder (wraps lock_holder_pid_alive)."""

    def test_returns_true_for_own_pid(self, tmp_path):
        """Returns True when lock file holds current process PID."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is True

    def test_returns_false_for_impossible_pid(self, tmp_path):
        """Returns False for a PID above the Linux max_pid limit."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{2 ** 22 + 1}\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is False

    def test_returns_false_when_lock_absent(self, tmp_path):
        """Returns False when .bob.lock does not exist."""
        lock = tmp_path / ".bob.lock"
        assert validate_lock_file_holder(lock) is False

    def test_returns_false_when_lock_empty(self, tmp_path):
        """Returns False when lock file has empty content."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("", encoding="utf-8")
        assert validate_lock_file_holder(lock) is False

    def test_returns_false_when_lock_corrupt(self, tmp_path):
        """Returns False when lock file has non-integer content."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("not-a-pid\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is False

    def test_reads_first_token(self, tmp_path):
        """Uses first whitespace-delimited token, ignores rest."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()} extra-ignored\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is True

    def test_accepts_string_path(self, tmp_path):
        """Accepts a string path argument."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert validate_lock_file_holder(str(lock)) is True

    def test_accepts_pathlib_path(self, tmp_path):
        """Accepts a pathlib.Path argument."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert validate_lock_file_holder(pathlib.Path(lock)) is True

    def test_returns_false_for_negative_pid(self, tmp_path):
        """Returns False for negative PID values."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("-1\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is False

    def test_returns_false_for_zero_pid(self, tmp_path):
        """Returns False for PID=0."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("0\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is False


# ---------------------------------------------------------------------------
# Three-signal gate integration (AC: integration: bob.orchestrator)
# ---------------------------------------------------------------------------

class TestThreeSignalGate:
    """Three-signal safe_to_remove_lock gate via bob.orchestrator.liveness_probe."""

    def test_safe_only_when_all_three_dead(self, tmp_path):
        """safe_to_remove_lock returns True only when all signals are False."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("99999\n")
        with (
            patch("bob.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
        ):
            assert safe_to_remove_lock(lock) is True

    def test_false_when_pgrep_signal_alive(self, tmp_path):
        """safe_to_remove_lock returns False when check_orchestrator_running is True."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("99999\n")
        with (
            patch("bob.orchestrator.liveness_probe.is_orchestrator_alive", return_value=True),
            patch("bob.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
        ):
            assert safe_to_remove_lock(lock) is False

    def test_false_when_lock_pid_alive(self, tmp_path):
        """safe_to_remove_lock returns False when validate_lock_file_holder is True."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("99999\n")
        with (
            patch("bob.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=True),
            patch("bob.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
        ):
            assert safe_to_remove_lock(lock) is False

    def test_false_when_db_has_executing_rows(self, tmp_path):
        """safe_to_remove_lock returns False when DB has recent executing rows."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("99999\n")
        with (
            patch("bob.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe._has_recent_executing_rows", return_value=True),
        ):
            assert safe_to_remove_lock(lock) is False

    def test_conservative_on_db_error(self, tmp_path):
        """safe_to_remove_lock returns False (conservative) on DB errors."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("99999\n")
        with (
            patch("bob.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
            patch("bob.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
            patch(
                "bob.orchestrator.liveness_probe._has_recent_executing_rows",
                side_effect=Exception("DB error"),
            ),
        ):
            assert safe_to_remove_lock(lock) is False

    def test_false_when_two_of_three_alive(self, tmp_path):
        """safe_to_remove_lock is False even with only 2 of 3 signals alive."""
        lock = tmp_path / ".bob.lock"
        lock.write_text("99999\n")
        with (
            patch("bob.orchestrator.liveness_probe.is_orchestrator_alive", return_value=True),
            patch("bob.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=True),
            patch("bob.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
        ):
            assert safe_to_remove_lock(lock) is False


# ---------------------------------------------------------------------------
# Integration: verify bob.liveness re-exports are the same functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# probe_matches_orchestrator tests (AC: bob.liveness.probe_matches_orchestrator)
# ---------------------------------------------------------------------------

class TestProbeMatchesOrchestrator:
    """Tests for probe_matches_orchestrator (regex-based bob[0-9]+ run match)."""

    def test_returns_true_for_bob14_run(self):
        """Matches 'bob14 run --all' as a live orchestrator."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(888_001, "bob14 run --all")],
        ):
            assert probe_matches_orchestrator() is True

    def test_returns_true_for_any_generation(self):
        """Matches bob[0-9]+ for any numeric suffix."""
        for gen in [1, 3, 14, 59, 100]:
            with patch(
                "bob.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[(888_002, f"bob{gen} run --all")],
            ):
                assert probe_matches_orchestrator() is True, f"Expected True for bob{gen}"

    def test_returns_true_for_path_prefixed_binary(self):
        """Matches '/usr/local/bin/bob14 run'."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(888_003, "/usr/local/bin/bob14 run")],
        ):
            assert probe_matches_orchestrator() is True

    def test_returns_false_when_no_matching_process(self):
        """Returns False when no orchestrator process found."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(888_004, "python scheduler.py")],
        ):
            assert probe_matches_orchestrator() is False

    def test_returns_false_for_empty_process_list(self):
        """Returns False on empty process list."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            assert probe_matches_orchestrator() is False

    def test_excludes_own_pid(self):
        """Does not count the current process as an external orchestrator."""
        own_pid = os.getpid()
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(own_pid, "bob14 run --all")],
        ):
            assert probe_matches_orchestrator() is False

    def test_excludes_shell_wrapper(self):
        """A bash process quoting 'bob17 run' is not an orchestrator."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(888_005, "bash -c 'bob17 run --all'")],
        ):
            assert probe_matches_orchestrator() is False

    def test_does_not_match_bare_bob(self):
        """'bob run --all' without digit suffix must not match."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(888_006, "bob run --all")],
        ):
            assert probe_matches_orchestrator() is False

    def test_returns_false_for_bob_without_run(self):
        """'bob14 status' is not an orchestrator."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(888_007, "bob14 status")],
        ):
            assert probe_matches_orchestrator() is False


# ---------------------------------------------------------------------------
# verify_db_activity tests (AC: bob.liveness.verify_db_activity)
# ---------------------------------------------------------------------------

class TestVerifyDbActivity:
    """Tests for verify_db_activity (DB executing-rows liveness signal)."""

    def test_returns_true_when_recent_executing_rows(self):
        """Returns True when DB has recent executing rows."""
        with patch(
            "bob.orchestrator.liveness_probe._has_recent_executing_rows",
            return_value=True,
        ):
            assert verify_db_activity() is True

    def test_returns_false_when_no_recent_executing_rows(self):
        """Returns False when DB has no recent executing rows."""
        with patch(
            "bob.orchestrator.liveness_probe._has_recent_executing_rows",
            return_value=False,
        ):
            assert verify_db_activity() is False

    def test_conservative_on_db_error(self):
        """Returns True (conservative) on DB errors."""
        with patch(
            "bob.orchestrator.liveness_probe._has_recent_executing_rows",
            side_effect=Exception("DB unavailable"),
        ):
            assert verify_db_activity() is True

    def test_accepts_db_path_kwarg(self, tmp_path):
        """Passes db_path through to the underlying implementation."""
        called_with = []

        def mock_check(db_path=None):
            called_with.append(db_path)
            return False

        with patch(
            "bob.orchestrator.liveness_probe._has_recent_executing_rows",
            side_effect=mock_check,
        ):
            result = verify_db_activity(db_path=tmp_path / "test.db")
        assert result is False
        assert len(called_with) == 1
        assert called_with[0] == tmp_path / "test.db"

    def test_returns_bool(self):
        """verify_db_activity always returns a bool."""
        with patch(
            "bob.orchestrator.liveness_probe._has_recent_executing_rows",
            return_value=True,
        ):
            result = verify_db_activity()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Integration: verify bob.liveness re-exports are the same functions
# ---------------------------------------------------------------------------

class TestLivenessModuleIntegration:
    """bob.liveness wrappers delegate to bob.orchestrator.liveness_probe."""

    def test_check_orchestrator_running_is_orchestrator_alive(self):
        """check_orchestrator_running delegates to is_orchestrator_alive."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(777_001, "bob59 run --all")],
        ):
            assert check_orchestrator_running() is True

    def test_validate_lock_file_holder_delegates_to_lock_holder_pid_alive(self, tmp_path):
        """validate_lock_file_holder delegates to lock_holder_pid_alive."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert validate_lock_file_holder(lock) is True

    def test_module_exports_all_ac_functions(self):
        """bob.liveness exports all AC-mandated functions."""
        import bob.liveness as m
        assert callable(m.probe_matches_orchestrator)
        assert callable(m.check_lock_file_holder)
        assert callable(m.verify_db_activity)
        assert callable(m.check_orchestrator_running)
        assert callable(m.validate_lock_file_holder)

    def test_probe_matches_orchestrator_delegates_to_is_orchestrator_alive(self):
        """probe_matches_orchestrator delegates to is_orchestrator_alive."""
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(777_002, "bob14 run --all")],
        ):
            assert probe_matches_orchestrator() is True

    def test_check_lock_file_holder_delegates_to_lock_holder_pid_alive(self, tmp_path):
        """check_lock_file_holder delegates to lock_holder_pid_alive."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert check_lock_file_holder(lock) is True

    def test_verify_db_activity_delegates_to_has_recent_executing_rows(self):
        """verify_db_activity delegates to _has_recent_executing_rows."""
        with patch(
            "bob.orchestrator.liveness_probe._has_recent_executing_rows",
            return_value=True,
        ):
            assert verify_db_activity() is True

    def test_verify_lock_file_holder_delegates_to_lock_holder_pid_alive(self, tmp_path):
        """verify_lock_file_holder (AC-mandated name) delegates to lock_holder_pid_alive."""
        lock = tmp_path / ".bob.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert verify_lock_file_holder(lock) is True

    def test_verify_lock_file_holder_returns_false_for_absent_lock(self, tmp_path):
        """verify_lock_file_holder returns False when lock file is absent."""
        lock = tmp_path / ".bob.lock"
        assert verify_lock_file_holder(lock) is False

    def test_module_exports_verify_lock_file_holder(self):
        """bob.liveness exports verify_lock_file_holder (AC: Function defined)."""
        import bob.liveness as m
        assert callable(m.verify_lock_file_holder)
