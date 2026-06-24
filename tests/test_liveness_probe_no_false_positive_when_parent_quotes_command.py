"""Tests: liveness probe no false positive when parent shell quotes bobN run.

Acceptance criterion:
    pytest: tests/test_liveness_probe_no_false_positive_when_parent_quotes_command.py
    asserts that when ancestry includes a shell whose argv contains 'bobN run'
    as a quoted literal, is_orchestrator_alive() returns False
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

from bob3.orchestrator.liveness_probe import is_orchestrator_alive


def _make_status_file(ppid: int) -> str:
    return f"Name:\tbash\nPid:\t999\nPPid:\t{ppid}\nTracerPid:\t0\n"


def test_no_false_positive_when_parent_bash_quotes_bobN_run():
    """Parent shell with 'bob17 run' in its eval string must NOT trigger alive=True."""
    own_pid = os.getpid()

    # Simulate: own_pid -> parent_shell_pid (bash whose cmdline contains bob17 run)
    parent_shell_pid = 999_001

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(parent_shell_pid),
        f"/proc/{parent_shell_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    # Parent bash whose argv contains "bob17 run" as a quoted literal
    fake_candidates = [
        (parent_shell_pid, "bash -c eval timeout 5 /home/yelkhamr/dark-factory/bob17/.venv/bin/bob17 run --all"),
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    # The parent bash is an ancestor AND a shell wrapper — must NOT be detected as alive orchestrator
    assert result is False


def test_no_false_positive_ancestry_shell_with_matching_cmdline():
    """Ancestor shell (non-direct parent) with bobN run in cmdline returns False."""
    own_pid = os.getpid()

    grandparent_shell_pid = 999_002
    parent_pid = 999_003

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(parent_pid),
        f"/proc/{parent_pid}/status": _make_status_file(grandparent_shell_pid),
        f"/proc/{grandparent_shell_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    fake_candidates = [
        (grandparent_shell_pid, "bash -c 'bob14 run --all'"),
        (parent_pid, "/bin/sh"),
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    assert result is False


def test_true_positive_independent_non_ancestor_bob_process():
    """An independent (non-ancestor) process with bob42 run --all IS alive."""
    own_pid = os.getpid()

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    independent_pid = 888_001
    fake_candidates = [
        (independent_pid, "/usr/bin/python3 /opt/bin/bob42 run --all"),
    ]

    with patch("builtins.open", side_effect=fake_open):
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=fake_candidates,
        ):
            result = is_orchestrator_alive()

    assert result is True
