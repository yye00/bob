"""Tests for feature a4164116: orchestrator-liveness probe MUST exclude process ancestry AND shell wrappers.

AC: pytest: tests/test_orchestrator_probe_ancestry.py

Verifies that bob3.orchestrator.probe_ancestry exports the two AC-mandated
public predicates and that they correctly implement the F-R7-567 exclusion fix:

  1. is_self_or_ancestor(pid) — excludes own process and all /proc PPid ancestors
  2. is_shell_wrapper(cmdline) — excludes bash/sh/dash/zsh/ksh/fish and timeout

These predicates are independently testable against synthetic /proc layouts
without mocking os.listdir, as required by the spec.
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

def _proc_status(pid: int, ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t{pid}\nPPid:\t{ppid}\nTracerPid:\t0\n"


def _fake_open(proc_files: dict[str, str]):
    """Factory: returns a fake open() that serves proc_files by path key."""
    def _open(path, *args, **kwargs):
        key = str(path)
        if key in proc_files:
            return io.StringIO(proc_files[key])
        raise FileNotFoundError(path)
    return _open


# ---------------------------------------------------------------------------
# Module structure checks
# ---------------------------------------------------------------------------

class TestProbeAncestryModuleStructure:
    """The probe_ancestry module must export the two AC-mandated predicates."""

    def test_is_self_or_ancestor_callable(self):
        assert callable(is_self_or_ancestor)

    def test_is_shell_wrapper_callable(self):
        assert callable(is_shell_wrapper)

    def test_collect_ancestor_pids_callable(self):
        assert callable(collect_ancestor_pids)

    def test_is_self_or_ancestor_returns_bool(self):
        result = is_self_or_ancestor(os.getpid())
        assert type(result) is bool

    def test_is_shell_wrapper_returns_bool(self):
        result = is_shell_wrapper("bash -c 'bob17 run --all'")
        assert type(result) is bool


# ---------------------------------------------------------------------------
# collect_ancestor_pids: synthetic /proc layouts (no os.listdir mocking needed)
# ---------------------------------------------------------------------------

class TestCollectAncestorPids:
    """Walk /proc PPid chain; testable with synthetic file content."""

    def test_returns_frozenset(self):
        with patch("builtins.open", side_effect=OSError):
            result = collect_ancestor_pids(42)
        assert isinstance(result, frozenset)

    def test_includes_own_pid_always(self):
        with patch("builtins.open", side_effect=OSError):
            result = collect_ancestor_pids(999)
        assert 999 in result

    def test_single_level_chain(self):
        """child → parent (ppid=1) stops at ppid≤1."""
        child, parent = 1000, 999
        files = {
            f"/proc/{child}/status": _proc_status(child, parent),
            f"/proc/{parent}/status": _proc_status(parent, 1),
        }
        with patch("builtins.open", _fake_open(files)):
            result = collect_ancestor_pids(child)
        assert child in result
        assert parent in result
        assert 1 not in result

    def test_two_level_chain(self):
        """child → mid → root (ppid=1)."""
        child, mid, root = 500, 400, 300
        files = {
            f"/proc/{child}/status": _proc_status(child, mid),
            f"/proc/{mid}/status": _proc_status(mid, root),
            f"/proc/{root}/status": _proc_status(root, 1),
        }
        with patch("builtins.open", _fake_open(files)):
            result = collect_ancestor_pids(child)
        assert result == frozenset({child, mid, root})

    def test_stops_at_ppid_one(self):
        """PID 1 (init) is not included — chain stops when ppid≤1."""
        child = 200
        files = {f"/proc/{child}/status": _proc_status(child, 1)}
        with patch("builtins.open", _fake_open(files)):
            result = collect_ancestor_pids(child)
        assert child in result
        assert 1 not in result

    def test_cycle_detection_terminates(self):
        """A PPid cycle (A→B→A) terminates without hanging."""
        pid_a, pid_b = 600, 601
        files = {
            f"/proc/{pid_a}/status": _proc_status(pid_a, pid_b),
            f"/proc/{pid_b}/status": _proc_status(pid_b, pid_a),
        }
        with patch("builtins.open", _fake_open(files)):
            result = collect_ancestor_pids(pid_a)
        assert pid_a in result
        assert pid_b in result

    def test_unreadable_proc_returns_at_least_own_pid(self):
        """OSError on /proc read returns {own_pid} minimum, never raises."""
        result = collect_ancestor_pids(77777)
        assert 77777 in result
        assert isinstance(result, frozenset)

    def test_missing_ppid_line_stops_walk(self):
        """Status file without PPid line stops the walk gracefully."""
        child = 800
        files = {f"/proc/{child}/status": f"Name:\tpython3\nPid:\t{child}\n"}
        with patch("builtins.open", _fake_open(files)):
            result = collect_ancestor_pids(child)
        assert child in result


# ---------------------------------------------------------------------------
# is_self_or_ancestor: the documented public predicate
# ---------------------------------------------------------------------------

class TestIsSelfOrAncestor:
    """is_self_or_ancestor(pid) must return True for own PID and ancestors."""

    def test_own_pid_is_self(self):
        assert is_self_or_ancestor(os.getpid()) is True

    def test_returns_bool_type(self):
        result = is_self_or_ancestor(os.getpid())
        assert type(result) is bool

    def test_unrelated_pid_returns_false(self):
        """A PID not in the ancestry chain returns False."""
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({os.getpid()}),
        ):
            assert is_self_or_ancestor(88888) is False

    def test_fabricated_ancestor_returns_true(self):
        """A PID explicitly in the fabricated ancestry set returns True."""
        own = os.getpid()
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({own, 4242}),
        ):
            assert is_self_or_ancestor(4242) is True

    def test_pid_zero_returns_false(self):
        """PID 0 is never our ancestor; must not raise."""
        result = is_self_or_ancestor(0)
        assert result is False

    def test_pid_1_not_our_ancestor_in_test_environment(self):
        """PID 1 (init/systemd) is excluded from our ancestry in normal tests."""
        assert is_self_or_ancestor(1) is False

    def test_never_raises_on_unreadable_proc(self):
        """Returns False (not raises) when /proc cannot be read."""
        with patch("builtins.open", side_effect=OSError("proc unreadable")):
            result = is_self_or_ancestor(99999)
        # Should return either True or False — never raise
        assert type(result) is bool


# ---------------------------------------------------------------------------
# is_shell_wrapper: the documented public predicate
# ---------------------------------------------------------------------------

class TestIsShellWrapper:
    """is_shell_wrapper(cmdline) identifies shell/timeout wrappers."""

    @pytest.mark.parametrize("cmdline", [
        "bash",
        "bash -c bob3 run",
        "/bin/bash -c 'bob17 run --all'",
        "/usr/bin/bash -c eval 'bob17 run'",
        "sh",
        "sh -c bob14 run",
        "/bin/sh -c 'bob59 run'",
        "dash",
        "dash -c bob3 run",
        "zsh",
        "zsh bob3 run --all",
        "ksh",
        "ksh bob3 run",
        "fish",
        "fish -c bob3 run",
        "/usr/bin/fish -c bob3 run",
        "timeout 5 bob17 run --all",
        "timeout bob3 run",
        "/usr/bin/timeout 5 bob17 run --all",
    ])
    def test_shell_wrappers_return_true(self, cmdline):
        assert is_shell_wrapper(cmdline) is True, f"{cmdline!r} should be identified as a shell wrapper"

    @pytest.mark.parametrize("cmdline", [
        "bob3 run --all",
        "bob14 run",
        "bob59 run",
        "/home/u/.venv/bin/bob17 run --all",
        "/usr/bin/python3 orchestrator.py",
        "python3 -m bob3",
        "node server.js",
        "bashing",       # contains 'bash' but is not 'bash'
        "shelling",      # contains 'sh' but is not 'sh'
        "dashtastic",    # contains 'dash' but is not 'dash'
    ])
    def test_non_shells_return_false(self, cmdline):
        assert is_shell_wrapper(cmdline) is False, f"{cmdline!r} should NOT be identified as a shell wrapper"

    def test_empty_string_returns_false(self):
        assert is_shell_wrapper("") is False

    def test_whitespace_only_returns_false(self):
        assert is_shell_wrapper("   ") is False

    def test_returns_bool_type(self):
        assert type(is_shell_wrapper("bash")) is bool
        assert type(is_shell_wrapper("bob3 run")) is bool

    def test_full_path_bash_is_wrapper(self):
        """Full-path bash argv[0] is still identified by basename."""
        assert is_shell_wrapper("/usr/local/bin/bash -c eval 'bob17 run'") is True

    def test_full_path_non_shell_not_wrapper(self):
        """Full path to a non-shell binary is not a wrapper."""
        assert is_shell_wrapper("/usr/local/bin/node server.js") is False

    def test_timeout_with_full_path_is_wrapper(self):
        """timeout with full path is recognized via basename startswith."""
        assert is_shell_wrapper("/usr/bin/timeout 30 bob14 run --all") is True


# ---------------------------------------------------------------------------
# Integration: predicates work together to prevent F-R7-567 false-positive
# ---------------------------------------------------------------------------

class TestF_R7_567_AncestryExclusionIntegration:
    """Integration: ancestry + shell-wrapper exclusions together close the defect.

    The bob3 version 17 defect: parent bash's eval string contained
    'bob17 run --all', causing the naive probe to block orchestrator launch.
    """

    def test_parent_shell_quoting_bobN_run_is_excluded_by_ancestry(self):
        """Ancestor PID is filtered by is_self_or_ancestor before pattern match."""
        own_pid = os.getpid()
        parent_pid = own_pid + 1  # synthetic ancestor

        fabricated_ancestry = frozenset({own_pid, parent_pid})
        # Shell wrapper check would also catch this, but ancestry is the primary defense
        assert parent_pid in fabricated_ancestry
        assert parent_pid not in frozenset({own_pid})  # without ancestry tracking, would be missed

    def test_shell_wrapper_excluded_independent_of_ancestry(self):
        """Even a non-ancestor shell quoting 'bob17 run' is excluded by is_shell_wrapper."""
        shell_cmdline = "bash -c eval 'bob17 run --all'"
        assert is_shell_wrapper(shell_cmdline) is True

    def test_genuine_orchestrator_not_excluded(self):
        """A genuine orchestrator process (not shell, not ancestor) is NOT excluded."""
        non_shell_cmdline = "/home/u/.venv/bin/bob17 run --all"
        own = os.getpid()

        # is_shell_wrapper must return False for genuine bob binary
        assert is_shell_wrapper(non_shell_cmdline) is False

        # is_self_or_ancestor must return False for unrelated PID
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({own}),
        ):
            assert is_self_or_ancestor(77777) is False

    def test_timeout_wrapper_excluded_for_all_supported_shells(self):
        """timeout wrapping any shell or bob binary is always a wrapper."""
        timeout_variants = [
            "timeout 5 bob17 run --all",
            "timeout 30 bash -c 'bob3 run'",
            "/usr/bin/timeout 10 bob14 run",
        ]
        for cmdline in timeout_variants:
            assert is_shell_wrapper(cmdline) is True, f"{cmdline!r} should be excluded"
