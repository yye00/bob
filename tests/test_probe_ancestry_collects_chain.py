"""Tests: collect_ancestor_pids builds a 3-level PPid chain correctly.

Acceptance criterion:
    pytest: tests/test_probe_ancestry_collects_chain.py asserts that with a
    3-level fake PPid chain, collect_ancestor_pids returns {leaf, mid, root}
"""

from __future__ import annotations

import builtins
import io
from unittest.mock import patch, mock_open

import pytest

from bob.orchestrator.probe_ancestry import collect_ancestor_pids


def _make_status_file(ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t999\nPPid:\t{ppid}\nTracerPid:\t0\n"


def test_collects_3_level_chain():
    """collect_ancestor_pids returns {leaf, mid, root} for a 3-level chain."""
    # Chain: leaf=300 -> mid=200 -> root=100 -> 1 (init, stop)
    leaf_pid = 300
    mid_pid = 200
    root_pid = 100

    proc_files = {
        f"/proc/{leaf_pid}/status": _make_status_file(mid_pid),
        f"/proc/{mid_pid}/status": _make_status_file(root_pid),
        f"/proc/{root_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    with patch("builtins.open", side_effect=fake_open):
        result = collect_ancestor_pids(leaf_pid)

    assert isinstance(result, frozenset)
    assert result == frozenset({leaf_pid, mid_pid, root_pid})


def test_collects_minimum_own_pid_when_proc_unreadable():
    """collect_ancestor_pids returns at minimum {own_pid} when /proc is absent."""
    own_pid = 12345

    with patch("builtins.open", side_effect=OSError("no proc")):
        result = collect_ancestor_pids(own_pid)

    assert own_pid in result
    assert isinstance(result, frozenset)


def test_collects_2_level_chain():
    """collect_ancestor_pids handles a simple 2-level chain (self -> parent -> 1)."""
    child_pid = 500
    parent_pid = 400

    proc_files = {
        f"/proc/{child_pid}/status": _make_status_file(parent_pid),
        f"/proc/{parent_pid}/status": _make_status_file(1),
    }

    def fake_open(path, *args, **kwargs):
        if str(path) in proc_files:
            return io.StringIO(proc_files[str(path)])
        raise FileNotFoundError(path)

    with patch("builtins.open", side_effect=fake_open):
        result = collect_ancestor_pids(child_pid)

    assert result == frozenset({child_pid, parent_pid})


def test_never_raises_on_missing_proc_entry():
    """collect_ancestor_pids never raises when /proc entries are missing."""
    # Should not raise even if every read fails
    with patch("builtins.open", side_effect=OSError("permission denied")):
        result = collect_ancestor_pids(9999)
    assert isinstance(result, frozenset)
    assert 9999 in result
