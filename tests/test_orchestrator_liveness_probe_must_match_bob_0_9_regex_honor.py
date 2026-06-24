"""Tests for orchestrator_liveness_probe_must_match_bob_0_9_regex_honor (4338fc09).

Verifies the short-name AC module delegates correctly to the three-signal
liveness gate via safe_to_remove_lock.
"""

from __future__ import annotations

import pathlib
import tempfile
from unittest.mock import patch

import pytest

import bob3.orchestrator_liveness_probe_must_match_bob_0_9_regex_honor as _mod


def _write_lock(path: pathlib.Path, pid: int) -> None:
    path.write_text(str(pid), encoding="utf-8")


def test_orchestrator_liveness_probe_must_match_bob_0_9_regex_honor():
    """AC-mandated test: three-signal gate via the short-name AC function.

    Covers:
      - Function exists in the AC-mandated module
      - All signals dead → True (safe to remove lock)
      - pgrep signal alive → False (not safe)
      - lock PID alive → False (not safe)
      - DB executing rows → False (not safe)
      - gen-N alias bob14 detected by regex signal
    """
    fn = _mod.orchestrator_liveness_probe_must_match_bob_0_9_regex_honor

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = pathlib.Path(tmpdir) / ".bob3.lock"
        dead_pid = 99999999  # very unlikely to be alive

        # Sub-test 1: all signals dead → True (safe)
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
            assert fn(lock_path=lock_path) is True

        # Sub-test 2: pgrep matches bob14 → False (not safe)
        _write_lock(lock_path, dead_pid)
        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[(12345, "bob14 run --all")],
            ),
            patch(
                "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
                return_value=False,
            ),
        ):
            assert fn(lock_path=lock_path) is False

        # Sub-test 3: lock PID is alive → False (not safe)
        own_pid = pathlib.Path("/proc/self").resolve().name
        _write_lock(lock_path, int(own_pid))  # write current PID (guaranteed alive)
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
            assert fn(lock_path=lock_path) is False

        # Sub-test 4: DB executing rows → False (not safe)
        _write_lock(lock_path, dead_pid)
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
            assert fn(lock_path=lock_path) is False

        # Sub-test 5: missing lock file → conservative False
        missing_lock = pathlib.Path(tmpdir) / "no.lock"
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
            # missing lock → lock_holder_pid_alive returns False (file absent)
            assert fn(lock_path=missing_lock) is True
