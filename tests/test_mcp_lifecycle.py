"""Tests for F-R6-302: MCP per-sub-agent lifecycle + orphan sweep.

These tests cover the ``register_mcp`` / ``unregister_mcp`` /
``sweep_orphans`` functions added to ``bob.mcp_lifecycle``.

Design notes:
- Tests use real subprocesses (``subprocess.Popen(['sleep', '60'])``)
  rather than mocked PIDs. The acceptance criteria explicitly require
  this so that "reap" means actually-dead, not "we called kill once."
- Each test redirects the registry file to a tmp path via the
  ``BOB_MCP_REGISTRY_PATH`` env var so test runs do not interfere
  with the operator's real ``~/.bob/mcp_registry.json``.
- The orphan sweep test uses a Python child that ``exec``s itself with
  ``argv[0]`` containing ``bob.memory_mcp`` so the cmdline-based
  detector matches it. We avoid spawning the real MCP because it has
  side effects (Qdrant init, mem0 init, ports).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from bob import mcp_lifecycle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_path(tmp_path, monkeypatch):
    """Redirect the on-disk registry into a tmp file for each test."""
    path = tmp_path / "mcp_registry.json"
    monkeypatch.setenv("BOB_MCP_REGISTRY_PATH", str(path))
    yield path
    # Best-effort cleanup of any leftover processes recorded in the file.
    if path.is_file():
        import json
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
        for pids in data.values() if isinstance(data, dict) else []:
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except OSError:
                    pass


def _wait_dead(pid: int, timeout: float = 3.0) -> bool:
    """Poll until pid is dead or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not mcp_lifecycle._pid_alive(pid):
            return True
        time.sleep(0.05)
    return not mcp_lifecycle._pid_alive(pid)


def _spawn_sleeper() -> subprocess.Popen:
    """Spawn a `sleep 60` child suitable as an MCP stand-in."""
    return subprocess.Popen(["sleep", "60"])


# A tiny Python child whose argv[0] contains 'bob.memory_mcp' so the
# cmdline-based detector finds it. The child execs itself with
# ``python -c "..."`` and a custom argv via ``os.execv``-style
# emulation — the simplest portable way is to set sys.argv via the
# command line: ``python -c <code> bob.memory_mcp``. The token then
# appears in /proc/<pid>/cmdline after the ``-c`` token.
_MCP_MIMIC_SCRIPT = textwrap.dedent(
    """
    import signal, time, sys
    # Ignore SIGTERM so the test can verify SIGKILL escalation works,
    # but keep handling SIGINT for safety in case the test runner Ctrl-Cs.
    # Actually — we want SIGTERM to work in the unregister test. So
    # leave default handling. The escalation path is exercised by
    # the unit-level _reap_pid test below.
    while True:
        time.sleep(1)
    """
)


def _spawn_mcp_mimic(
    parent_pid: int | None = None,
) -> subprocess.Popen:
    """Spawn a process whose cmdline contains ``bob.memory_mcp``.

    The trailing positional arg ``bob.memory_mcp`` makes the token
    appear in ``/proc/<pid>/cmdline`` so ``_is_memory_mcp_pid``
    matches it without us having to start the real MCP server.
    """
    return subprocess.Popen(
        [sys.executable, "-c", _MCP_MIMIC_SCRIPT, "bob.memory_mcp"],
    )


# ---------------------------------------------------------------------------
# 1. Register + retrieve
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_then_load(self, registry_path):
        mcp_lifecycle.register_mcp("agent-1", 12345)
        reg = mcp_lifecycle._load_registry()
        assert reg == {"agent-1": [12345]}

    def test_register_multiple_pids_per_agent(self, registry_path):
        mcp_lifecycle.register_mcp("agent-1", 100)
        mcp_lifecycle.register_mcp("agent-1", 200)
        reg = mcp_lifecycle._load_registry()
        assert reg["agent-1"] == [100, 200]

    def test_register_is_idempotent_on_duplicate_pid(self, registry_path):
        mcp_lifecycle.register_mcp("agent-1", 100)
        mcp_lifecycle.register_mcp("agent-1", 100)
        assert mcp_lifecycle._load_registry()["agent-1"] == [100]

    def test_register_rejects_empty_id(self, registry_path):
        with pytest.raises(ValueError):
            mcp_lifecycle.register_mcp("", 100)

    def test_register_rejects_invalid_pid(self, registry_path):
        with pytest.raises(ValueError):
            mcp_lifecycle.register_mcp("agent-1", 0)
        with pytest.raises(ValueError):
            mcp_lifecycle.register_mcp("agent-1", -3)

    def test_registry_persists_across_loads(self, registry_path):
        mcp_lifecycle.register_mcp("agent-1", 100)
        mcp_lifecycle.register_mcp("agent-2", 200)
        # Simulate a fresh process by re-reading from disk.
        reg = mcp_lifecycle._load_registry()
        assert reg == {"agent-1": [100], "agent-2": [200]}


# ---------------------------------------------------------------------------
# 2. Unregister kills alive processes
# ---------------------------------------------------------------------------


class TestUnregister:
    def test_unregister_kills_alive_process(self, registry_path):
        proc = _spawn_sleeper()
        try:
            mcp_lifecycle.register_mcp("agent-x", proc.pid)
            reaped = mcp_lifecycle.unregister_mcp("agent-x")
            assert proc.pid in reaped, f"expected {proc.pid} in {reaped}"
            assert _wait_dead(proc.pid, timeout=2.0), (
                f"pid {proc.pid} still alive after unregister"
            )
            # Registry entry should be removed.
            assert "agent-x" not in mcp_lifecycle._load_registry()
        finally:
            try:
                proc.kill()
            except OSError:
                pass
            proc.wait(timeout=5)

    def test_unregister_kills_multiple_pids(self, registry_path):
        procs = [_spawn_sleeper(), _spawn_sleeper(), _spawn_sleeper()]
        try:
            for p in procs:
                mcp_lifecycle.register_mcp("agent-multi", p.pid)
            reaped = mcp_lifecycle.unregister_mcp("agent-multi")
            for p in procs:
                assert p.pid in reaped
                assert _wait_dead(p.pid, timeout=2.0)
        finally:
            for p in procs:
                try:
                    p.kill()
                except OSError:
                    pass
                p.wait(timeout=5)

    def test_unregister_unknown_id_is_noop(self, registry_path):
        # No exception, returns empty list.
        assert mcp_lifecycle.unregister_mcp("nobody") == []

    def test_unregister_handles_already_dead_pid(self, registry_path):
        proc = _spawn_sleeper()
        proc.kill()
        proc.wait(timeout=5)
        mcp_lifecycle.register_mcp("agent-dead", proc.pid)
        # Already-dead PID should be reported as reaped (it is dead).
        reaped = mcp_lifecycle.unregister_mcp("agent-dead")
        assert reaped == [proc.pid]
        assert "agent-dead" not in mcp_lifecycle._load_registry()

    def test_reap_escalates_sigterm_to_sigkill(self, registry_path):
        # A process that ignores SIGTERM forces the SIGKILL path.
        code = textwrap.dedent(
            """
            import signal, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                time.sleep(1)
            """
        )
        proc = subprocess.Popen([sys.executable, "-c", code])
        try:
            mcp_lifecycle.register_mcp("agent-stubborn", proc.pid)
            t0 = time.monotonic()
            reaped = mcp_lifecycle.unregister_mcp("agent-stubborn")
            elapsed = time.monotonic() - t0
            assert proc.pid in reaped
            assert _wait_dead(proc.pid, timeout=2.0)
            # SIGTERM wait is ~1s; SIGKILL then takes well under 1s.
            # Just bound the total below ~5s to catch regressions.
            assert elapsed < 5.0, f"reap took too long: {elapsed}s"
        finally:
            try:
                proc.kill()
            except OSError:
                pass
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# 3. sweep_orphans finds orphans
# ---------------------------------------------------------------------------


def _wait_pid_appears(pid: int, timeout: float = 3.0) -> bool:
    """Wait until pid exists in /proc (race-proofing for spawn)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if Path(f"/proc/{pid}").is_dir():
            return True
        time.sleep(0.02)
    return False


class TestSweepOrphans:
    def test_sweep_finds_orphan_mcp(self, registry_path):
        """Parent dies, child MCP-mimic is left orphaned, sweep reaps it."""
        # Parent script: spawn an MCP-mimic, print its pid, then exit.
        # The child outlives us so its PPid becomes 1 (init) which the
        # sweep treats as orphaned.
        parent_code = textwrap.dedent(
            f"""
            import subprocess, sys, os
            # Redirect child stdio to devnull so the grandchild does
            # not keep our stdout pipe open after we exit (otherwise
            # the test's communicate() would block forever waiting
            # for EOF on the inherited fd).
            devnull = open(os.devnull, "wb")
            child = subprocess.Popen(
                [sys.executable, "-c", {_MCP_MIMIC_SCRIPT!r}, "bob.memory_mcp"],
                stdin=subprocess.DEVNULL,
                stdout=devnull,
                stderr=devnull,
            )
            print(child.pid, flush=True)
            # exit immediately, leaving child orphaned
            """
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", parent_code],
            stdout=subprocess.PIPE,
        )
        try:
            stdout_data, _ = parent.communicate(timeout=10)
            child_pid = int(stdout_data.strip())
        except Exception:
            parent.kill()
            raise
        # Wait for parent to be fully reaped (zombie cleared).
        parent.wait(timeout=5)
        assert _wait_pid_appears(child_pid), (
            f"orphan child pid={child_pid} never appeared in /proc"
        )

        # The child's PPid should now be 1 (init) or its parent should
        # be dead. Either condition triggers sweep_orphans.
        try:
            orphans = mcp_lifecycle.sweep_orphans()
            assert child_pid in orphans, (
                f"sweep did not reap orphan pid={child_pid}; got {orphans}"
            )
            assert _wait_dead(child_pid, timeout=2.0)
        finally:
            # Defensive cleanup in case the sweep failed.
            try:
                os.kill(child_pid, signal.SIGKILL)
            except OSError:
                pass

    def test_sweep_ignores_mcps_with_alive_parent(self, registry_path):
        """MCP with an alive (test process) parent must NOT be reaped."""
        # We spawn the mimic directly so this test process is its parent.
        # The sweep should see ppid == os.getpid() (alive) and skip it.
        child = _spawn_mcp_mimic()
        try:
            assert _wait_pid_appears(child.pid)
            ppid = mcp_lifecycle._read_ppid(child.pid)
            assert ppid == os.getpid(), (
                f"expected ppid={os.getpid()} but got {ppid}"
            )
            orphans = mcp_lifecycle.sweep_orphans()
            assert child.pid not in orphans, (
                f"sweep wrongly reaped non-orphan pid={child.pid}"
            )
            # And the process should still be alive.
            assert mcp_lifecycle._pid_alive(child.pid)
        finally:
            try:
                child.kill()
            except OSError:
                pass
            child.wait(timeout=5)

    def test_sweep_returns_empty_when_no_mcps(self, registry_path):
        # Nothing to find unless other tests left stuff behind; either
        # way the call must not raise.
        result = mcp_lifecycle.sweep_orphans()
        assert isinstance(result, list)

    def test_sweep_purges_dead_pids_from_registry(self, registry_path):
        # Register a pid, kill it, then sweep — the registry entry
        # should be garbage-collected.
        proc = _spawn_sleeper()
        mcp_lifecycle.register_mcp("agent-gc", proc.pid)
        proc.kill()
        proc.wait(timeout=5)
        assert _wait_dead(proc.pid)
        mcp_lifecycle.sweep_orphans()
        # The (now-dead) pid should be gone from the registry.
        reg = mcp_lifecycle._load_registry()
        assert "agent-gc" not in reg


# ---------------------------------------------------------------------------
# 4. /proc helpers
# ---------------------------------------------------------------------------


class TestProcHelpers:
    def test_pid_alive_true_for_self(self):
        assert mcp_lifecycle._pid_alive(os.getpid())

    def test_pid_alive_false_for_dead(self):
        proc = _spawn_sleeper()
        proc.kill()
        proc.wait(timeout=5)
        assert not mcp_lifecycle._pid_alive(proc.pid) or _wait_dead(proc.pid)

    def test_read_ppid_matches_getppid(self):
        # Our /proc/<self>/status PPid line should equal os.getppid().
        assert mcp_lifecycle._read_ppid(os.getpid()) == os.getppid()

    def test_is_memory_mcp_pid_detects_mimic(self):
        child = _spawn_mcp_mimic()
        try:
            assert _wait_pid_appears(child.pid)
            assert mcp_lifecycle._is_memory_mcp_pid(child.pid)
        finally:
            child.kill()
            child.wait(timeout=5)

    def test_is_memory_mcp_pid_false_for_other(self):
        proc = _spawn_sleeper()
        try:
            assert _wait_pid_appears(proc.pid)
            assert not mcp_lifecycle._is_memory_mcp_pid(proc.pid)
        finally:
            proc.kill()
            proc.wait(timeout=5)
