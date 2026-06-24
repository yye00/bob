"""Tests that is_stale detects orchestrator files newer than process start time."""

from __future__ import annotations

import os
import time
import pathlib

import pytest

from bob.orchestrator.stale_bytecode_guard import is_stale, check_freshness


@pytest.fixture()
def workspace(tmp_path):
    orch_dir = tmp_path / "src" / "bob" / "orchestrator"
    orch_dir.mkdir(parents=True)
    return tmp_path, orch_dir


def test_is_stale_returns_true_when_file_newer_than_start(workspace):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# new code")
    # File is brand-new; start_time is 60s ago
    start_time = time.time() - 60
    assert is_stale(tmp_path, start_time) is True


def test_is_stale_returns_false_when_all_files_older(workspace):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# old code")
    old_mtime = time.time() - 120
    os.utime(py_file, (old_mtime, old_mtime))
    # process started 60s ago, file is 120s old
    start_time = time.time() - 60
    assert is_stale(tmp_path, start_time) is False


def test_is_stale_returns_false_when_no_lock_file_and_no_start_time(workspace):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# code")
    # No start_time and no lock_file → conservatively False (cannot determine)
    assert is_stale(tmp_path) is False


def test_is_stale_detects_multiple_new_files(workspace):
    tmp_path, orch_dir = workspace
    (orch_dir / "a.py").write_text("# a")
    (orch_dir / "b.py").write_text("# b")
    start_time = time.time() - 60
    assert is_stale(tmp_path, start_time) is True


def test_is_stale_with_one_new_among_old_files(workspace):
    """Even one newer file among several older ones triggers True."""
    tmp_path, orch_dir = workspace
    start_time = time.time() - 30

    old_mtime = time.time() - 60
    old_file = orch_dir / "old_module.py"
    old_file.write_text("# old")
    os.utime(old_file, (old_mtime, old_mtime))

    # New file written after start_time
    new_file = orch_dir / "new_module.py"
    new_file.write_text("# new")
    future_mtime = time.time() + 5
    os.utime(new_file, (future_mtime, future_mtime))

    assert is_stale(tmp_path, start_time) is True


def test_check_freshness_returns_correct_stale_paths(workspace):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "spawn_dispatcher.py"
    py_file.write_text("# dispatcher")
    start_time = time.time() - 60
    stale = check_freshness(tmp_path, start_time)
    assert len(stale) == 1
    assert stale[0] == py_file


def test_check_freshness_excludes_non_py_files(workspace):
    tmp_path, orch_dir = workspace
    (orch_dir / "README.txt").write_text("docs")
    (orch_dir / "config.json").write_text("{}")
    start_time = time.time() - 60
    stale = check_freshness(tmp_path, start_time)
    assert stale == []


def test_is_stale_with_lock_file(workspace):
    import json
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# new")
    lock_file = tmp_path / ".bob.lock"
    started_at = time.time() - 60
    lock_file.write_text(json.dumps({"pid": 1234, "started_at": started_at}))
    assert is_stale(tmp_path, lock_file=lock_file) is True
