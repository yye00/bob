"""Tests for SpawnWatchdog context manager (feature 02345742-56fa-4ecf-8dd6-f956cc796f96)."""
from __future__ import annotations

import os
import signal
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import json

import pytest

from bob3.spawn_watchdog import SpawnWatchdog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeProc:
    """Minimal subprocess.Popen stand-in."""

    def __init__(self, pid: int = 12345, will_timeout: bool = False):
        self.pid = pid
        self._will_timeout = will_timeout
        self.returncode: int | None = None
        self._killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self._will_timeout and timeout is not None:
            raise TimeoutError
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9
        self._killed = True


# ---------------------------------------------------------------------------
# Construction & attribute tests
# ---------------------------------------------------------------------------

def test_spawn_watchdog_instantiation():
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, timeout_s=3600, feature_id="feat-1")
    assert w is not None


def test_spawn_watchdog_reads_timeout_from_env(tmp_path, monkeypatch):
    """BOB3_CRITERION_EXEC_TIMEOUT overrides the default when not supplied."""
    monkeypatch.setenv("BOB3_CRITERION_EXEC_TIMEOUT", "7200")
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, feature_id="feat-1")
    assert w.timeout_s == 7200


def test_spawn_watchdog_explicit_timeout_wins_over_env(monkeypatch):
    monkeypatch.setenv("BOB3_CRITERION_EXEC_TIMEOUT", "7200")
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, timeout_s=1800, feature_id="feat-1")
    assert w.timeout_s == 1800


def test_spawn_watchdog_default_timeout_when_env_unset(monkeypatch):
    monkeypatch.delenv("BOB3_CRITERION_EXEC_TIMEOUT", raising=False)
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, feature_id="feat-1")
    # Should use a sensible default (e.g. 3600s = 1 hour)
    assert w.timeout_s > 0


# ---------------------------------------------------------------------------
# Context manager protocol
# ---------------------------------------------------------------------------

def test_context_manager_enters_and_exits_without_raising(tmp_path):
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, timeout_s=60, feature_id="feat-1",
                      progress_path=tmp_path / "progress.jsonl")
    with w:
        pass  # proc completes immediately (returncode already None → poll returns None but wait returns 0)


def test_context_manager_sets_timed_out_false_on_normal_exit(tmp_path):
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, timeout_s=60, feature_id="feat-1",
                      progress_path=tmp_path / "progress.jsonl")
    with w:
        pass
    assert w.timed_out is False


# ---------------------------------------------------------------------------
# Heartbeat emission
# ---------------------------------------------------------------------------

def test_heartbeat_written_to_progress_jsonl(tmp_path):
    """SpawnWatchdog emits heartbeat events to the progress JSONL file."""
    progress_path = tmp_path / ".bob3" / "progress.jsonl"
    proc = _FakeProc()

    w = SpawnWatchdog(
        proc=proc,
        timeout_s=60,
        feature_id="feat-hb",
        progress_path=progress_path,
        heartbeat_interval_s=0.05,  # very short for tests
    )

    with w:
        time.sleep(0.15)  # allow at least 2 heartbeats

    assert progress_path.exists(), "progress.jsonl should be created"
    lines = [ln for ln in progress_path.read_text().splitlines() if ln.strip()]
    heartbeats = [json.loads(ln) for ln in lines if json.loads(ln).get("event_type") == "heartbeat"]
    assert len(heartbeats) >= 1, f"Expected ≥1 heartbeat, got {len(heartbeats)}"


def test_heartbeat_contains_required_fields(tmp_path):
    progress_path = tmp_path / "progress.jsonl"
    proc = _FakeProc()

    w = SpawnWatchdog(
        proc=proc,
        timeout_s=60,
        feature_id="feat-fields",
        progress_path=progress_path,
        heartbeat_interval_s=0.05,
    )
    with w:
        time.sleep(0.1)

    lines = [ln for ln in progress_path.read_text().splitlines() if ln.strip()]
    heartbeats = [json.loads(ln) for ln in lines if json.loads(ln).get("event_type") == "heartbeat"]
    assert heartbeats, "No heartbeat events found"

    hb = heartbeats[0]
    assert "timestamp" in hb
    assert "feature_id" in hb
    assert hb["feature_id"] == "feat-fields"
    assert "payload" in hb


# ---------------------------------------------------------------------------
# Timeout: SIGTERM then SIGKILL
# ---------------------------------------------------------------------------

def test_timeout_sends_sigterm_then_sigkill(tmp_path, monkeypatch):
    """On wall-clock timeout: SIGTERM first, then SIGKILL if process persists."""
    progress_path = tmp_path / "progress.jsonl"
    term_calls = []
    kill_calls = []

    class _HangingProc:
        pid = 99999
        returncode = None

        def poll(self):
            return None  # never finishes

        def terminate(self):
            term_calls.append(True)

        def kill(self):
            kill_calls.append(True)
            self.returncode = -9

        def wait(self, timeout=None):
            if term_calls and not kill_calls:
                # Still "alive" after SIGTERM — simulate stubborn process
                raise TimeoutError
            return -9

    proc = _HangingProc()
    w = SpawnWatchdog(
        proc=proc,
        timeout_s=0.1,
        feature_id="feat-timeout",
        progress_path=progress_path,
        heartbeat_interval_s=9999,
        sigkill_grace_s=0.05,
    )
    with w:
        time.sleep(0.3)  # longer than timeout

    assert term_calls, "SIGTERM should have been sent"
    assert kill_calls, "SIGKILL should have been sent after grace period"
    assert w.timed_out is True


def test_timeout_records_event_in_progress_jsonl(tmp_path):
    progress_path = tmp_path / "progress.jsonl"

    class _HangingProc:
        pid = 99998
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            raise TimeoutError

    proc = _HangingProc()
    w = SpawnWatchdog(
        proc=proc,
        timeout_s=0.1,
        feature_id="feat-timeout-record",
        progress_path=progress_path,
        heartbeat_interval_s=9999,
        sigkill_grace_s=0.05,
    )
    with w:
        time.sleep(0.3)

    lines = [ln for ln in progress_path.read_text().splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]
    timeout_events = [e for e in events if e.get("event_type") == "spawn_timeout"]
    assert len(timeout_events) >= 1, f"Expected spawn_timeout event, got events: {[e['event_type'] for e in events]}"


def test_timeout_event_contains_feature_id(tmp_path):
    progress_path = tmp_path / "progress.jsonl"

    class _HangingProc:
        pid = 99997
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            raise TimeoutError

    proc = _HangingProc()
    w = SpawnWatchdog(
        proc=proc,
        timeout_s=0.1,
        feature_id="feat-timeout-fields",
        progress_path=progress_path,
        heartbeat_interval_s=9999,
        sigkill_grace_s=0.05,
    )
    with w:
        time.sleep(0.3)

    lines = [ln for ln in progress_path.read_text().splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]
    timeout_events = [e for e in events if e.get("event_type") == "spawn_timeout"]
    assert timeout_events
    te = timeout_events[0]
    assert te["feature_id"] == "feat-timeout-fields"


# ---------------------------------------------------------------------------
# Process-group kill (POSIX)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "posix", reason="Process groups are POSIX-only")
def test_uses_process_group_kill_on_posix(tmp_path, monkeypatch):
    """On timeout, killpg is used instead of kill() to kill the whole process group."""
    progress_path = tmp_path / "progress.jsonl"
    killpg_calls = []

    class _HangingProc:
        pid = 55555
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            raise TimeoutError

    proc = _HangingProc()

    original_killpg = os.killpg
    def fake_killpg(pgid, sig):
        killpg_calls.append((pgid, sig))

    monkeypatch.setattr(os, "killpg", fake_killpg)
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)

    w = SpawnWatchdog(
        proc=proc,
        timeout_s=0.1,
        feature_id="feat-pgroup",
        progress_path=progress_path,
        heartbeat_interval_s=9999,
        sigkill_grace_s=0.05,
    )
    with w:
        time.sleep(0.3)

    assert any(sig == signal.SIGKILL for _, sig in killpg_calls), \
        f"Expected SIGKILL via killpg, got calls: {killpg_calls}"


# ---------------------------------------------------------------------------
# Normal completion (no timeout)
# ---------------------------------------------------------------------------

def test_no_timeout_when_process_exits_quickly(tmp_path):
    progress_path = tmp_path / "progress.jsonl"
    proc = _FakeProc()

    w = SpawnWatchdog(
        proc=proc,
        timeout_s=30,
        feature_id="feat-quick",
        progress_path=progress_path,
        heartbeat_interval_s=9999,
    )
    with w:
        pass  # proc finishes before timeout

    assert w.timed_out is False

    if progress_path.exists():
        lines = [ln for ln in progress_path.read_text().splitlines() if ln.strip()]
        events = [json.loads(ln) for ln in lines]
        timeout_events = [e for e in events if e.get("event_type") == "spawn_timeout"]
        assert len(timeout_events) == 0, "No timeout event should be emitted on clean exit"


# ---------------------------------------------------------------------------
# Integration: env var default timeout
# ---------------------------------------------------------------------------

def test_default_timeout_integrates_with_env_var(tmp_path, monkeypatch):
    """When BOB3_CRITERION_EXEC_TIMEOUT is set, SpawnWatchdog uses it as default timeout."""
    monkeypatch.setenv("BOB3_CRITERION_EXEC_TIMEOUT", "9999")
    proc = _FakeProc()
    w = SpawnWatchdog(proc=proc, feature_id="feat-env")
    assert w.timeout_s == 9999
