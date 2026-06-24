"""Tests for bob3.orchestrator.probe_ancestry.

Covers:
- collect_ancestor_pids: chain walking, cycle detection, OSError resilience
- is_self_or_ancestor: own PID, ancestor PID, unrelated PID
- is_shell_wrapper: all shell basenames, timeout, full paths, non-shell binaries

All tests use synthetic /proc data; no unittest.mock.patch of os.listdir needed.
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

from bob3.orchestrator.probe_ancestry import (
    collect_ancestor_pids,
    is_self_or_ancestor,
    is_shell_wrapper,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status(ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t1\nPPid:\t{ppid}\nTracerPid:\t0\n"


def _fake_open(proc_files: dict[str, str]):
    def _open(path, *args, **kwargs):
        key = str(path)
        if key in proc_files:
            return io.StringIO(proc_files[key])
        raise FileNotFoundError(path)
    return _open


# ---------------------------------------------------------------------------
# collect_ancestor_pids
# ---------------------------------------------------------------------------

class TestCollectAncestorPids:
    def test_returns_frozenset(self):
        with patch("builtins.open", side_effect=OSError):
            result = collect_ancestor_pids(999)
        assert isinstance(result, frozenset)

    def test_includes_own_pid(self):
        with patch("builtins.open", side_effect=OSError):
            result = collect_ancestor_pids(42)
        assert 42 in result

    def test_two_level_chain(self):
        child, parent = 500, 400
        files = {
            f"/proc/{child}/status": _status(parent),
            f"/proc/{parent}/status": _status(1),
        }
        with patch("builtins.open", side_effect=_fake_open(files)):
            result = collect_ancestor_pids(child)
        assert result == frozenset({child, parent})

    def test_three_level_chain(self):
        leaf, mid, root = 300, 200, 100
        files = {
            f"/proc/{leaf}/status": _status(mid),
            f"/proc/{mid}/status": _status(root),
            f"/proc/{root}/status": _status(1),
        }
        with patch("builtins.open", side_effect=_fake_open(files)):
            result = collect_ancestor_pids(leaf)
        assert result == frozenset({leaf, mid, root})

    def test_stops_at_pid_1(self):
        child, parent = 700, 1
        files = {f"/proc/{child}/status": _status(parent)}
        with patch("builtins.open", side_effect=_fake_open(files)):
            result = collect_ancestor_pids(child)
        assert child in result
        assert 1 not in result

    def test_cycle_terminates(self):
        own, mid = 50, 100
        files = {
            f"/proc/{own}/status": _status(mid),
            f"/proc/{mid}/status": _status(mid),
        }
        with patch("builtins.open", side_effect=_fake_open(files)):
            result = collect_ancestor_pids(own)
        assert own in result
        assert mid in result

    def test_missing_proc_entry_does_not_raise(self):
        with patch("builtins.open", side_effect=OSError("no proc")):
            result = collect_ancestor_pids(12345)
        assert 12345 in result


# ---------------------------------------------------------------------------
# is_self_or_ancestor
# ---------------------------------------------------------------------------

class TestIsSelfOrAncestor:
    def test_own_pid_is_self_or_ancestor(self):
        own = os.getpid()
        assert is_self_or_ancestor(own) is True

    def test_unrelated_pid_is_not_ancestor(self):
        # PID 2 is a kernel thread; will not be in our ancestry tree
        assert is_self_or_ancestor(2) is False

    def test_ancestor_pid_returns_true(self):
        own = os.getpid()
        # Fabricate a fake ancestry that includes PID 9999
        fake_ancestry = frozenset({own, 9999})
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=fake_ancestry,
        ):
            assert is_self_or_ancestor(9999) is True

    def test_non_ancestor_pid_returns_false(self):
        own = os.getpid()
        fake_ancestry = frozenset({own, 1234})
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=fake_ancestry,
        ):
            assert is_self_or_ancestor(5678) is False

    def test_returns_bool(self):
        result = is_self_or_ancestor(os.getpid())
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# is_shell_wrapper
# ---------------------------------------------------------------------------

class TestIsShellWrapper:
    @pytest.mark.parametrize("shell", ["bash", "sh", "dash", "zsh", "ksh", "fish"])
    def test_bare_shell_name_is_wrapper(self, shell):
        assert is_shell_wrapper(shell) is True

    @pytest.mark.parametrize("shell", ["bash", "sh", "dash", "zsh", "ksh", "fish"])
    def test_full_path_shell_is_wrapper(self, shell):
        assert is_shell_wrapper(f"/bin/{shell}") is True

    def test_timeout_is_wrapper(self):
        assert is_shell_wrapper("timeout 5 bob14 run") is True

    def test_timeout_full_path_is_wrapper(self):
        assert is_shell_wrapper("/usr/bin/timeout 5 bob14 run") is True

    def test_python_is_not_wrapper(self):
        assert is_shell_wrapper("python3 -m bob3") is False

    def test_bob14_run_is_not_wrapper(self):
        assert is_shell_wrapper("bob14 run --all") is False

    def test_empty_string_returns_false(self):
        assert is_shell_wrapper("") is False

    def test_shell_with_args_is_wrapper(self):
        assert is_shell_wrapper("bash -c 'bob17 run --all'") is True

    def test_returns_bool(self):
        assert isinstance(is_shell_wrapper("bash"), bool)

    def test_non_shell_executable_not_wrapper(self):
        assert is_shell_wrapper("/usr/local/bin/node server.js") is False

    def test_partial_shell_name_not_wrapper(self):
        # 'bashing' should not match even though it contains 'bash'
        assert is_shell_wrapper("bashing") is False
