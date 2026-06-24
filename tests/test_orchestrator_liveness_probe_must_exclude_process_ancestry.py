"""Tests for feature 34ace496: orchestrator-liveness probe MUST exclude process ancestry AND shell wrappers.

Verifies that:
  - The AC-mandated module and function exist and are callable
  - Ancestor PIDs (parent, grandparent, …) are excluded from the pgrep scan
  - Shell wrappers (bash/sh/dash/zsh/ksh/fish/timeout) are excluded even when
    their argv contains a bobN-run command string
  - Non-ancestor, non-shell processes matching the pattern ARE detected
  - The predicates is_self_or_ancestor and is_shell_wrapper are independently
    testable against synthetic /proc layouts
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

import bob3.orchestrator_liveness_probe_must_exclude_process_ancestry as _mod
from bob3.orchestrator.probe_ancestry import (
    collect_ancestor_pids,
    is_self_or_ancestor,
    is_shell_wrapper,
)

_FN_NAME = "orchestrator_liveness_probe_must_exclude_process_ancestry"
_probe = getattr(_mod, _FN_NAME)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_proc_status(pid: int, ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t{pid}\nPPid:\t{ppid}\nTracerPid:\t0\n"


def _make_open_factory(proc_files: dict[str, str]):
    """Return a fake open() that serves proc_files; raises FileNotFoundError otherwise."""
    def _open(path, *args, **kwargs):
        key = str(path)
        if key in proc_files:
            return io.StringIO(proc_files[key])
        raise FileNotFoundError(path)
    return _open


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

class TestModuleStructure:
    """AC-mandated module and function must exist."""

    def test_module_importable(self):
        assert _mod is not None

    def test_function_defined(self):
        assert callable(_probe)

    def test_function_name(self):
        assert _probe.__name__ == _FN_NAME

    def test_returns_bool(self):
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            result = _probe()
        assert type(result) is bool


# ---------------------------------------------------------------------------
# Main AC test (single function name mandated by AC)
# ---------------------------------------------------------------------------

def test_orchestrator_liveness_probe_must_exclude_process_ancestry():
    """AC-mandated test: ancestry and shell-wrapper exclusions prevent false positives.

    Covers:
      1. Ancestor shells quoting 'bobN run' in their eval string are NOT detected.
      2. Shell wrapper processes (bash/sh/dash/zsh/ksh/fish/timeout) are excluded.
      3. A genuine unrelated process running 'bobN run' IS detected.
      4. All signals dead → probe returns False (no orchestrator running).
    """
    own_pid = os.getpid()

    # --- Sub-test 1: ancestor shell quoting 'bob17 run' NOT detected ---
    # Simulates the bob3 version 17 defect: parent bash's eval contains
    # "bob17 run --all" but is not itself a running orchestrator.
    parent_pid = own_pid + 1  # synthetic parent

    with patch(
        "bob3.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[
            (parent_pid, "bash -c eval 'bob17 run --all'"),
        ],
    ), patch(
        "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
        return_value=frozenset({own_pid, parent_pid}),
    ):
        result = _probe()
    assert result is False, (
        "Parent shell quoting 'bob17 run' MUST NOT be detected as a live orchestrator"
    )

    # --- Sub-test 2: shell wrapper argv[0] is excluded even without ancestry ---
    for shell_cmd in [
        "bash -c bob3 run",
        "sh -c bob14 run --all",
        "dash -c 'bob59 run'",
        "zsh bob3 run",
        "ksh bob3 run",
        "fish -c bob3 run",
        "timeout 5 bob17 run --all",
    ]:
        unrelated_pid = 88001
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(unrelated_pid, shell_cmd)],
        ), patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({own_pid}),
        ):
            result = _probe()
        assert result is False, (
            f"Shell wrapper {shell_cmd!r} MUST be excluded from pgrep scan"
        )

    # --- Sub-test 3: genuine orchestrator IS detected ---
    genuine_pid = 77777  # not an ancestor, not a shell wrapper
    with patch(
        "bob3.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[(genuine_pid, "/home/u/.venv/bin/bob17 run --all")],
    ), patch(
        "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
        return_value=frozenset({own_pid}),
    ):
        result = _probe()
    assert result is True, (
        "Genuine remote orchestrator process MUST be detected as alive"
    )

    # --- Sub-test 4: no candidate processes → probe returns False ---
    with patch(
        "bob3.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[],
    ):
        result = _probe()
    assert result is False, "No matching processes → probe must return False"

    # --- Sub-test 5: gen-N aliases (bob14, bob59, bob100) are detected ---
    for alias_cmd in ["bob14 run --all", "bob59 run", "/path/to/bob100 run --all"]:
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(66666, alias_cmd)],
        ), patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({own_pid}),
        ):
            result = _probe()
        assert result is True, f"Alias {alias_cmd!r} must be detected as a live orchestrator"

    # --- Sub-test 6: own_pid is excluded ---
    with patch(
        "bob3.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[(own_pid, "bob3 run --all")],
    ):
        result = _probe()
    assert result is False, "Own PID must always be excluded from the pgrep scan"


# ---------------------------------------------------------------------------
# collect_ancestor_pids: synthetic /proc layouts
# ---------------------------------------------------------------------------

class TestCollectAncestorPids:
    """collect_ancestor_pids traces the PPid chain without mocking os.listdir."""

    def test_own_pid_included(self):
        own = os.getpid()
        ancestry = collect_ancestor_pids(own)
        assert own in ancestry

    def test_returns_frozenset(self):
        own = os.getpid()
        result = collect_ancestor_pids(own)
        assert isinstance(result, frozenset)

    def test_synthetic_two_level_chain(self):
        """3-process chain: 500 → 200 → 100 (init) stops at ppid ≤ 1."""
        proc_files = {
            "/proc/500/status": _fake_proc_status(500, 200),
            "/proc/200/status": _fake_proc_status(200, 1),
        }
        with patch("builtins.open", _make_open_factory(proc_files)):
            ancestry = collect_ancestor_pids(500)
        assert 500 in ancestry
        assert 200 in ancestry
        # ppid=1 (init) stops the walk
        assert 1 not in ancestry

    def test_cycle_detection_does_not_hang(self):
        """A PPid cycle (A→B→A) terminates without infinite recursion."""
        proc_files = {
            "/proc/300/status": _fake_proc_status(300, 301),
            "/proc/301/status": _fake_proc_status(301, 300),  # cycle
        }
        with patch("builtins.open", _make_open_factory(proc_files)):
            ancestry = collect_ancestor_pids(300)
        assert 300 in ancestry
        assert 301 in ancestry

    def test_unreadable_proc_returns_own_pid(self):
        """If /proc is unreadable, result is {own_pid} at minimum."""

        def _raise(path, *args, **kwargs):
            raise OSError("proc unreadable")

        with patch("builtins.open", _raise):
            ancestry = collect_ancestor_pids(9999)
        assert 9999 in ancestry
        assert len(ancestry) >= 1


# ---------------------------------------------------------------------------
# is_self_or_ancestor
# ---------------------------------------------------------------------------

class TestIsSelfOrAncestor:
    """is_self_or_ancestor(pid) is the documented public predicate."""

    def test_own_pid_is_self(self):
        assert is_self_or_ancestor(os.getpid()) is True

    def test_returns_bool_type(self):
        result = is_self_or_ancestor(os.getpid())
        assert type(result) is bool

    def test_unrelated_pid_false(self):
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({os.getpid()}),
        ):
            assert is_self_or_ancestor(99999) is False

    def test_fabricated_ancestor_true(self):
        own = os.getpid()
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({own, 4242}),
        ):
            assert is_self_or_ancestor(4242) is True

    def test_pid_1_is_not_ancestor(self):
        """PID 1 (init/systemd) is not our ancestor in normal test environments."""
        assert is_self_or_ancestor(1) is False


# ---------------------------------------------------------------------------
# is_shell_wrapper
# ---------------------------------------------------------------------------

class TestIsShellWrapper:
    """is_shell_wrapper(cmdline) is the documented public predicate."""

    @pytest.mark.parametrize("cmdline", [
        "bash -c bob3 run",
        "sh -c bob14 run",
        "dash -c 'bob59 run'",
        "zsh bob3 run --all",
        "ksh bob3 run",
        "fish -c bob3 run",
        "/usr/bin/bash -c bob17 run",
        "timeout 5 bob17 run --all",
        "timeout bob3 run",
    ])
    def test_shell_wrappers_return_true(self, cmdline):
        assert is_shell_wrapper(cmdline) is True, f"{cmdline!r} should be a shell wrapper"

    @pytest.mark.parametrize("cmdline", [
        "bob3 run --all",
        "bob14 run",
        "/home/u/.venv/bin/bob17 run --all",
        "/usr/bin/python3 orchestrator.py",
        "",
    ])
    def test_non_shells_return_false(self, cmdline):
        assert is_shell_wrapper(cmdline) is False, f"{cmdline!r} should NOT be a shell wrapper"

    def test_empty_cmdline_returns_false(self):
        assert is_shell_wrapper("") is False

    def test_returns_bool_type(self):
        result = is_shell_wrapper("bash -c bob3 run")
        assert type(result) is bool
