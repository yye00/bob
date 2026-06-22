"""Tests: lock_holder_pid_alive parses .bob3.lock PID and probes it.

Acceptance criterion:
    pytest: tests/test_liveness_probe_lock_pid_alive.py asserts
    lock_holder_pid_alive returns True for current-process PID and
    False for a never-allocated PID.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from bob3.orchestrator.liveness_probe import lock_holder_pid_alive


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_lock_holder_pid_alive_true_for_own_pid(tmp_path):
    """lock_holder_pid_alive returns True when lock file holds current PID."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is True


def test_lock_holder_pid_alive_false_for_never_allocated_pid(tmp_path):
    """lock_holder_pid_alive returns False for a PID that cannot exist (max+1)."""
    # Use PID 2^22 which is above the Linux max_pid limit (typically 4194304)
    # so it will never be alive on any Linux system.
    impossible_pid = 2 ** 22 + 1
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text(f"{impossible_pid}\n", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is False


def test_lock_holder_pid_alive_false_when_lock_absent(tmp_path):
    """lock_holder_pid_alive returns False when .bob3.lock does not exist."""
    lock_file = tmp_path / ".bob3.lock"
    assert lock_holder_pid_alive(lock_file) is False


def test_lock_holder_pid_alive_false_when_lock_empty(tmp_path):
    """lock_holder_pid_alive returns False when lock file has no PID."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is False


def test_lock_holder_pid_alive_false_when_lock_corrupt(tmp_path):
    """lock_holder_pid_alive returns False when lock file has non-integer content."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("not-a-pid\n", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is False


def test_lock_holder_pid_alive_reads_first_token(tmp_path):
    """lock_holder_pid_alive uses the first whitespace-delimited token."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text(f"{os.getpid()} extra-content-ignored\n", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is True


def test_lock_holder_pid_alive_accepts_path_object(tmp_path):
    """lock_holder_pid_alive accepts pathlib.Path argument."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert lock_holder_pid_alive(pathlib.Path(lock_file)) is True


def test_lock_holder_pid_alive_accepts_string_path(tmp_path):
    """lock_holder_pid_alive accepts string argument."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert lock_holder_pid_alive(str(lock_file)) is True


def test_lock_holder_pid_alive_negative_pid_returns_false(tmp_path):
    """lock_holder_pid_alive returns False for negative PID values."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("-1\n", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is False


def test_lock_holder_pid_alive_zero_pid_returns_false(tmp_path):
    """lock_holder_pid_alive returns False for PID=0."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("0\n", encoding="utf-8")
    assert lock_holder_pid_alive(lock_file) is False
