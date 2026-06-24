"""Tests for bob.orchestrator.probe_ancestry.

Covers:
- collect_ancestor_pids: chain walking, cycle detection, OSError resilience
- is_self_or_ancestor: own PID, ancestor PID, unrelated PID
- is_shell_wrapper: all shell basenames, timeout, full paths, non-shell binaries

All tests use synthetic /proc data — no unittest.mock.patch of os.listdir needed.
The predicates are independently testable against injected data, satisfying the
F-R7-580 requirement that exclusion logic be separately exercisable.
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

from bob.orchestrator.probe_ancestry import (
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
        child = 700
        files = {f"/proc/{child}/status": _status(1)}
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

    def test_returns_minimum_own_pid_on_ioerror(self):
        """Even when /proc is completely unreadable, own_pid is always returned."""
        with patch("builtins.open", side_effect=IOError):
            result = collect_ancestor_pids(77)
        assert result == frozenset({77})


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
        fake_ancestry = frozenset({own, 9999})
        with patch(
            "bob.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=fake_ancestry,
        ):
            assert is_self_or_ancestor(9999) is True

    def test_non_ancestor_pid_returns_false(self):
        own = os.getpid()
        fake_ancestry = frozenset({own, 1234})
        with patch(
            "bob.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=fake_ancestry,
        ):
            assert is_self_or_ancestor(5678) is False

    def test_returns_bool(self):
        result = is_self_or_ancestor(os.getpid())
        assert isinstance(result, bool)

    def test_uses_own_pid_for_ancestry_lookup(self):
        """is_self_or_ancestor passes os.getpid() into collect_ancestor_pids."""
        own = os.getpid()
        captured = []

        def fake_collect(pid):
            captured.append(pid)
            return frozenset({pid})

        with patch(
            "bob.orchestrator.probe_ancestry.collect_ancestor_pids",
            side_effect=fake_collect,
        ):
            is_self_or_ancestor(42)

        assert captured == [own]


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

    def test_timeout_bare_is_wrapper(self):
        assert is_shell_wrapper("timeout 5 bob14 run") is True

    def test_timeout_full_path_is_wrapper(self):
        assert is_shell_wrapper("/usr/bin/timeout 5 bob14 run") is True

    def test_python_is_not_wrapper(self):
        assert is_shell_wrapper("python3 -m bob") is False

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
        # 'bashing' starts with 'bash' in the string but basename is 'bashing'
        assert is_shell_wrapper("bashing") is False

    def test_eval_string_with_bob_run_is_not_itself_wrapper(self):
        """
        This is the exact failure mode from F-R7-567/F-R7-580:
        The cmdline 'bash -c eval timeout 5 bob17 run --all' is a shell wrapper
        because argv[0] is 'bash'. The test confirms is_shell_wrapper returns True,
        meaning is_orchestrator_alive WILL skip it.
        """
        cmdline = "bash -c eval 'timeout 5 /home/yelkhamr/dark-factory/bob17/.venv/bin/bob17 run --all'"
        assert is_shell_wrapper(cmdline) is True

    def test_timeout_variant_names(self):
        """timeout-like binaries (e.g., timeout.real) should also be excluded."""
        assert is_shell_wrapper("timeout.real 10 bob63 run") is True
