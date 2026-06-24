"""Tests: collect_ancestor_pids terminates on self-referential PPid (cycle).

Acceptance criterion:
    pytest: tests/test_probe_ancestry_breaks_on_cycle.py asserts that a
    self-referential PPid (pid 100 -> PPid 100) terminates without infinite
    loop and returns {own_pid, 100}
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from bob.orchestrator.probe_ancestry import collect_ancestor_pids


def _make_status_file(ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t100\nPPid:\t{ppid}\nTracerPid:\t0\n"


def test_self_referential_ppid_terminates():
    """Self-referential PPid (pid 100 -> PPid 100) does not loop infinitely."""
    own_pid = 50  # the process we start from
    mid_pid = 100  # has PPid pointing to itself

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(mid_pid),
        f"/proc/{mid_pid}/status": _make_status_file(mid_pid),  # self-referential
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    with patch("builtins.open", side_effect=fake_open):
        result = collect_ancestor_pids(own_pid)

    # Must terminate and include both own_pid and 100
    assert isinstance(result, frozenset)
    assert own_pid in result
    assert mid_pid in result


def test_direct_self_cycle():
    """A process whose own PPid equals its own pid terminates immediately."""
    own_pid = 100

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(own_pid),  # self-loop
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    with patch("builtins.open", side_effect=fake_open):
        result = collect_ancestor_pids(own_pid)

    assert isinstance(result, frozenset)
    assert own_pid in result


def test_longer_cycle_terminates():
    """A longer cycle (A->B->C->A) terminates correctly."""
    own_pid = 10
    pid_a = 20
    pid_b = 30
    pid_c = pid_a  # cycle: b points back to a

    proc_files = {
        f"/proc/{own_pid}/status": _make_status_file(pid_a),
        f"/proc/{pid_a}/status": _make_status_file(pid_b),
        f"/proc/{pid_b}/status": _make_status_file(pid_c),  # -> pid_a (cycle)
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    with patch("builtins.open", side_effect=fake_open):
        result = collect_ancestor_pids(own_pid)

    assert isinstance(result, frozenset)
    assert own_pid in result
    assert pid_a in result
    assert pid_b in result
