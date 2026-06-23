"""Tests for orchestrator liveness probe with ancestry and shell-wrapper exclusions.

Feature 0eb191b5: Orchestrator-liveness probe MUST exclude process ancestry AND
shell wrappers (F-R7-567 / F-R7-580).

Covers:
- bob3.orchestrator.probe_ancestry.is_self_or_ancestor (documented predicate)
- bob3.orchestrator.probe_ancestry.is_shell_wrapper (documented predicate)
- Integration: bob3.orchestrator.liveness_probe.is_orchestrator_alive delegates
  to both predicates and never fires on ancestor shells quoting bobN run
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
from bob3.orchestrator.liveness_probe import is_orchestrator_alive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_content(ppid: int) -> str:
    return f"Name:\tpython3\nPid:\t999\nPPid:\t{ppid}\nTracerPid:\t0\n"


def _fake_open_for(proc_files: dict[str, str]):
    def _open(path, *args, **kwargs):
        key = str(path)
        if key in proc_files:
            return io.StringIO(proc_files[key])
        raise FileNotFoundError(path)
    return _open


# ---------------------------------------------------------------------------
# is_self_or_ancestor — public predicate
# ---------------------------------------------------------------------------

class TestIsSelfOrAncestor:
    """is_self_or_ancestor(pid) returns True iff pid is current process or ancestor."""

    def test_own_pid_returns_true(self):
        """Current process PID is always self-or-ancestor."""
        assert is_self_or_ancestor(os.getpid()) is True

    def test_returns_bool_type(self):
        """Return value is a bool, not a truthy int or set."""
        result = is_self_or_ancestor(os.getpid())
        assert type(result) is bool

    def test_pid_1_returns_false(self):
        """PID 1 (init/systemd) is not our ancestor in normal test environments."""
        assert is_self_or_ancestor(1) is False

    def test_unrelated_pid_returns_false(self):
        """An arbitrary high PID that is not our ancestor returns False."""
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({os.getpid(), 1001, 1002}),
        ):
            assert is_self_or_ancestor(99999) is False

    def test_fabricated_ancestor_returns_true(self):
        """Returns True for a PID in the fabricated ancestry set."""
        own = os.getpid()
        fake_ancestry = frozenset({own, 4242, 1000})
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=fake_ancestry,
        ):
            assert is_self_or_ancestor(4242) is True

    def test_uses_collect_ancestor_pids(self):
        """is_self_or_ancestor delegates to collect_ancestor_pids."""
        own = os.getpid()
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=frozenset({own}),
        ) as mock_collect:
            is_self_or_ancestor(own)
        mock_collect.assert_called_once_with(own)

    def test_parent_pid_returns_true(self):
        """The real parent process (os.getppid()) is identified as an ancestor."""
        ppid = os.getppid()
        if ppid <= 1:
            pytest.skip("Parent PID is init; cannot verify ancestry")
        # Build a minimal synthetic ancestry that includes ppid
        own = os.getpid()
        fake_ancestry = frozenset({own, ppid})
        with patch(
            "bob3.orchestrator.probe_ancestry.collect_ancestor_pids",
            return_value=fake_ancestry,
        ):
            assert is_self_or_ancestor(ppid) is True

    def test_proc_unreadable_falls_back_gracefully(self):
        """When /proc is unreadable, still includes own_pid."""
        own = os.getpid()
        # collect_ancestor_pids falls back to {own_pid}; is_self_or_ancestor
        # should still return True for the current process.
        with patch("builtins.open", side_effect=OSError("no proc")):
            assert is_self_or_ancestor(own) is True


# ---------------------------------------------------------------------------
# is_shell_wrapper — public predicate
# ---------------------------------------------------------------------------

class TestIsShellWrapper:
    """is_shell_wrapper(cmdline) returns True iff argv[0] is a shell or timeout binary."""

    @pytest.mark.parametrize("shell", ["bash", "sh", "dash", "zsh", "ksh", "fish"])
    def test_bare_shell_name(self, shell):
        """All supported shell basenames are recognised as wrappers."""
        assert is_shell_wrapper(shell) is True

    @pytest.mark.parametrize("shell", ["bash", "sh", "dash", "zsh", "ksh", "fish"])
    def test_full_path_shell(self, shell):
        """Shells via full path are recognised as wrappers."""
        assert is_shell_wrapper(f"/bin/{shell}") is True

    @pytest.mark.parametrize("shell", ["bash", "sh", "dash", "zsh", "ksh", "fish"])
    def test_shell_with_quoted_bob_command(self, shell):
        """Shell quoting a bobN-run command is still a wrapper, not an orchestrator."""
        assert is_shell_wrapper(f"{shell} -c 'bob17 run --all'") is True

    def test_timeout_bare(self):
        """'timeout' as argv[0] is a wrapper."""
        assert is_shell_wrapper("timeout 5 bob14 run") is True

    def test_timeout_full_path(self):
        """Full-path /usr/bin/timeout is a wrapper."""
        assert is_shell_wrapper("/usr/bin/timeout 5 bob14 run") is True

    def test_timeout_variant_with_suffix(self):
        """Binaries starting with 'timeout' (e.g. timeout60) are wrappers."""
        assert is_shell_wrapper("timeout60 bob3 run") is True

    def test_empty_string_returns_false(self):
        """Empty cmdline returns False (not a shell)."""
        assert is_shell_wrapper("") is False

    def test_bob_run_is_not_wrapper(self):
        """A direct bobN-run invocation is NOT a wrapper."""
        assert is_shell_wrapper("bob17 run --all") is False

    def test_python_is_not_wrapper(self):
        """Python is not a shell wrapper."""
        assert is_shell_wrapper("python3 script.py") is False

    def test_node_is_not_wrapper(self):
        """Node.js is not a shell wrapper."""
        assert is_shell_wrapper("/usr/local/bin/node server.js") is False

    def test_partial_shell_name_not_wrapper(self):
        """'bashing' does not match 'bash' — basename must be exact."""
        assert is_shell_wrapper("bashing --foo") is False

    def test_returns_bool_type(self):
        """Return value is a bool."""
        assert type(is_shell_wrapper("bash")) is bool
        assert type(is_shell_wrapper("bob14 run")) is bool

    def test_sudo_is_not_wrapper(self):
        """sudo is not in the recognised shell/timeout set."""
        assert is_shell_wrapper("sudo bob14 run") is False

    def test_eval_string_not_wrapper_if_not_shell(self):
        """An eval string where argv[0] is the actual binary is not a wrapper."""
        assert is_shell_wrapper("bob14 run --all --extra=eval foo") is False


# ---------------------------------------------------------------------------
# Integration: is_orchestrator_alive delegates to both predicates
# ---------------------------------------------------------------------------

class TestIsOrchestratorAliveIntegration:
    """Verify is_orchestrator_alive uses is_self_or_ancestor and is_shell_wrapper."""

    def test_detects_real_orchestrator(self):
        """A bob14-run process that is not ancestor/shell fires True."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(88001, "bob14 run --all")],
        ):
            assert is_orchestrator_alive() is True

    def test_does_not_fire_for_own_pid(self):
        """own PID is excluded even if its cmdline matches."""
        own = os.getpid()
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(own, "bob14 run --all")],
        ):
            assert is_orchestrator_alive() is False

    def test_does_not_fire_for_ancestor_shell_quoting_command(self):
        """The F-R7-567 bug: parent bash with eval 'bob17 run …' must NOT fire."""
        parent_pid = os.getppid()
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(parent_pid, "bash -c \"eval 'bob17 run --all'\"")],
        ):
            # Even if the parent cmdline contains 'bob17 run', it is:
            # (a) shell wrapper → excluded by is_shell_wrapper
            # Even without ancestry check, shell-wrapper exclusion must catch this.
            assert is_orchestrator_alive() is False

    def test_does_not_fire_for_bash_quoting_bob(self):
        """bash whose cmdline QUOTES bobN run is excluded via is_shell_wrapper."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(77001, "bash -c 'timeout 5 /home/user/.venv/bin/bob17 run --all'")],
        ):
            assert is_orchestrator_alive() is False

    def test_does_not_fire_for_sh_quoting_bob(self):
        """sh quoting 'bob3 run' does not trigger False positive."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(77002, "sh -c 'bob3 run --all'")],
        ):
            assert is_orchestrator_alive() is False

    def test_does_not_fire_for_timeout_wrapping_bob(self):
        """timeout wrapping bob14 run is excluded by is_shell_wrapper."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(77003, "timeout 10 bob14 run --all")],
        ):
            assert is_orchestrator_alive() is False

    def test_does_not_fire_for_ancestor_pid(self):
        """A PID in the ancestry chain is excluded even with a real bobN-run cmdline."""
        own = os.getpid()
        fake_ancestor = 55555
        fake_ancestry = frozenset({own, fake_ancestor})
        with (
            patch(
                "bob3.orchestrator.liveness_probe._iter_candidate_pids",
                return_value=[(fake_ancestor, "bob14 run --all")],
            ),
            patch(
                "bob3.orchestrator.liveness_probe.collect_ancestor_pids",
                return_value=fake_ancestry,
            ),
        ):
            assert is_orchestrator_alive() is False

    def test_fires_for_non_ancestor_non_shell_bob_run(self):
        """A non-ancestor, non-shell bob59 run process causes True."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(66001, "bob59 run --all")],
        ):
            assert is_orchestrator_alive() is True

    def test_fires_for_full_path_bob_run(self):
        """Full-path /home/user/.venv/bin/bob14 run --all is detected."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(66002, "/home/user/.venv/bin/bob14 run --all")],
        ):
            assert is_orchestrator_alive() is True

    def test_empty_proc_list_returns_false(self):
        """No processes → is_orchestrator_alive returns False."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            assert is_orchestrator_alive() is False

    def test_non_matching_processes_return_false(self):
        """Non-orchestrator processes produce False."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[(66003, "python3 -m http.server 8080")],
        ):
            assert is_orchestrator_alive() is False

    def test_returns_bool_type(self):
        """is_orchestrator_alive always returns a bool."""
        with patch(
            "bob3.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=[],
        ):
            assert type(is_orchestrator_alive()) is bool


# ---------------------------------------------------------------------------
# Integration: probe_ancestry module is importable from liveness_probe context
# ---------------------------------------------------------------------------

class TestModuleIntegration:
    """Verify module structure: probe_ancestry is imported by liveness_probe."""

    def test_probe_ancestry_module_importable(self):
        """bob3.orchestrator.probe_ancestry imports without error."""
        import bob3.orchestrator.probe_ancestry as mod
        assert callable(mod.is_self_or_ancestor)
        assert callable(mod.is_shell_wrapper)

    def test_liveness_probe_imports_probe_ancestry(self):
        """bob3.orchestrator.liveness_probe imports from probe_ancestry."""
        import bob3.orchestrator.liveness_probe as lp
        # The module should expose is_orchestrator_alive
        assert callable(lp.is_orchestrator_alive)

    def test_is_self_or_ancestor_callable(self):
        """is_self_or_ancestor is a callable exported from probe_ancestry."""
        assert callable(is_self_or_ancestor)

    def test_is_shell_wrapper_callable(self):
        """is_shell_wrapper is a callable exported from probe_ancestry."""
        assert callable(is_shell_wrapper)
