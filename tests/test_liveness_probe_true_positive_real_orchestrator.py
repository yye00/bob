"""Tests: liveness probe true positive — real independent orchestrator process.

Acceptance criterion:
    pytest: tests/test_liveness_probe_true_positive_real_orchestrator.py asserts
    that an independent (non-ancestor, non-shell) process with cmdline
    '/usr/bin/python3 /opt/bin/bob42 run --all' is correctly detected as alive
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

from bob.orchestrator.liveness_probe import is_orchestrator_alive


def _make_status_file(ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t999\nPPid:\t{ppid}\nTracerPid:\t0\n"


def test_true_positive_python3_bob42_run():
    """An independent python3 /opt/bin/bob42 run --all process is detected alive."""
    own_pid = os.getpid()

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    independent_pid = 77777
    fake_candidates = [
        (independent_pid, "/usr/bin/python3 /opt/bin/bob42 run --all"),
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    assert result is True


def test_true_positive_bare_bob17_run():
    """A non-ancestor, non-shell process 'bob17 run --all' is detected alive."""
    own_pid = os.getpid()

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    independent_pid = 55555
    fake_candidates = [
        (independent_pid, "bob17 run --all"),
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    assert result is True


def test_false_when_only_process_is_shell_wrapper():
    """Returns False when only matching process is a shell wrapper."""
    own_pid = os.getpid()

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    shell_pid = 66666
    fake_candidates = [
        (shell_pid, "bash -c 'bob17 run --all'"),
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    assert result is False


def test_false_when_all_processes_excluded():
    """Returns False when all matching processes are shells or ancestors."""
    own_pid = os.getpid()

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    fake_candidates = [
        (own_pid, "bob22 run --all"),  # own pid excluded
        (44444, "bash -c 'bob17 run'"),  # shell wrapper excluded
        (44445, "/bin/sh timeout 10 bob14 run"),  # shell wrapper excluded
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    assert result is False
