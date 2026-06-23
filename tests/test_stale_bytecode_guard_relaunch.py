"""Tests for stale-bytecode guard at relaunch (feature e6c0019a-9c17-48e3-a7ad-63f233d48a50).

Verifies that stale_bytecode_guard_relaunch correctly compares mtime of every
orchestrator source file against the previous bob_N process start time, and
signals whether kill+relaunch is required even when the DB looks recoverable.
"""

from __future__ import annotations

import json
import os
import pathlib
import time

import pytest

from bob3.stale_bytecode_guard_relaunch import stale_bytecode_guard_relaunch


@pytest.fixture()
def workspace(tmp_path):
    """Create a minimal workspace with src/bob3/orchestrator/ directory."""
    orch_dir = tmp_path / "src" / "bob3" / "orchestrator"
    orch_dir.mkdir(parents=True)
    lock_file = tmp_path / ".bob3.lock"
    return tmp_path, orch_dir, lock_file


def _write_lock(lock_file: pathlib.Path, started_at: float, pid: int = 1234) -> None:
    lock_file.write_text(json.dumps({"pid": pid, "started_at": started_at}))


def test_stale_bytecode_guard_relaunch_returns_true_when_file_newer(workspace):
    """Returns True when an orchestrator .py file is newer than process start."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 60
    _write_lock(lock_file, started_at)

    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# new code")
    # file mtime is now (> started_at)

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is True


def test_stale_bytecode_guard_relaunch_returns_false_when_all_older(workspace):
    """Returns False when all orchestrator .py files predate process start."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 30
    _write_lock(lock_file, started_at)

    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# old code")
    old_mtime = time.time() - 120
    os.utime(py_file, (old_mtime, old_mtime))

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is False


def test_stale_bytecode_guard_relaunch_no_py_files(workspace):
    """Returns False when orchestrator dir has no .py files."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 60
    _write_lock(lock_file, started_at)

    (orch_dir / "README.txt").write_text("docs")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is False


def test_stale_bytecode_guard_relaunch_missing_lock_file(workspace):
    """Returns True (conservative) when .bob3.lock does not exist."""
    tmp_path, orch_dir, lock_file = workspace
    # Do NOT write lock file

    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# code")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is True


def test_stale_bytecode_guard_relaunch_detects_one_stale_among_many(workspace):
    """Returns True even when only one file among many is stale."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 30
    _write_lock(lock_file, started_at)

    old_mtime = time.time() - 120
    for name in ["a.py", "b.py", "c.py"]:
        f = orch_dir / name
        f.write_text("# old")
        os.utime(f, (old_mtime, old_mtime))

    # One newer file
    new_file = orch_dir / "d.py"
    new_file.write_text("# new")
    future_mtime = time.time() + 10
    os.utime(new_file, (future_mtime, future_mtime))

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is True


def test_stale_bytecode_guard_relaunch_non_py_files_ignored(workspace):
    """Non-.py files are never counted as stale."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 60
    _write_lock(lock_file, started_at)

    (orch_dir / "config.json").write_text("{}")
    (orch_dir / "schema.sql").write_text("CREATE TABLE x (id int);")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is False


def test_stale_bytecode_guard_relaunch_multiple_bob_dirs(tmp_path):
    """Checks all src/bob*/orchestrator/ dirs, not just bob3."""
    for gen in ["bob3", "bob4", "bob12"]:
        orch_dir = tmp_path / "src" / gen / "orchestrator"
        orch_dir.mkdir(parents=True)

    lock_file = tmp_path / ".bob3.lock"
    started_at = time.time() - 60
    _write_lock(lock_file, started_at)

    # Write a new .py in bob12's orchestrator
    new_file = tmp_path / "src" / "bob12" / "orchestrator" / "run_loop.py"
    new_file.write_text("# fresh")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is True


def test_stale_bytecode_guard_relaunch_no_orchestrator_dirs(tmp_path):
    """Returns False when no src/bob*/orchestrator/ dirs exist at all."""
    lock_file = tmp_path / ".bob3.lock"
    _write_lock(lock_file, time.time() - 60)

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is False


def test_stale_bytecode_guard_relaunch_old_lock_format(workspace):
    """Returns True (conservative) when lock file uses plain-PID format (no started_at)."""
    tmp_path, orch_dir, lock_file = workspace
    lock_file.write_text("12345")  # old plain-PID format

    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# code")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is True


def test_stale_bytecode_guard_relaunch_with_explicit_start_time(workspace):
    """Accepts an explicit start_time float instead of reading lock file."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 60

    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# new code")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file=None, start_time=started_at)
    assert result is True


def test_stale_bytecode_guard_relaunch(workspace):
    """AC canonical test: function returns True when orchestrator file is newer than start."""
    tmp_path, orch_dir, lock_file = workspace
    started_at = time.time() - 60
    _write_lock(lock_file, started_at)

    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# implementation under test")

    result = stale_bytecode_guard_relaunch(tmp_path, lock_file)
    assert result is True
