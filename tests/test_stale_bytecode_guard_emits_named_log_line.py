"""Tests that log_stale_file and check_freshness emit named log lines."""

from __future__ import annotations

import logging
import os
import time
import pathlib

import pytest

from bob3.orchestrator.stale_bytecode_guard import log_stale_file, check_freshness


@pytest.fixture()
def workspace(tmp_path):
    orch_dir = tmp_path / "src" / "bob3" / "orchestrator"
    orch_dir.mkdir(parents=True)
    return tmp_path, orch_dir


def test_log_stale_file_emits_warning(workspace, caplog):
    tmp_path, orch_dir = workspace
    stale_path = orch_dir / "run_loop.py"
    stale_path.write_text("# code")
    mtime = time.time()
    start_time = mtime - 60
    with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.stale_bytecode_guard"):
        log_stale_file(stale_path, mtime, start_time)
    assert len(caplog.records) >= 1
    assert caplog.records[-1].levelno == logging.WARNING


def test_log_stale_file_names_the_path(workspace, caplog):
    tmp_path, orch_dir = workspace
    stale_path = orch_dir / "spawn_dispatcher.py"
    stale_path.write_text("# dispatcher")
    mtime = time.time()
    start_time = mtime - 30
    with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.stale_bytecode_guard"):
        log_stale_file(stale_path, mtime, start_time)
    messages = [r.getMessage() for r in caplog.records]
    assert any("spawn_dispatcher.py" in msg for msg in messages)


def test_check_freshness_logs_stale_file_name(workspace, caplog):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# stale")
    start_time = time.time() - 60
    with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.stale_bytecode_guard"):
        check_freshness(tmp_path, start_time)
    messages = [r.getMessage() for r in caplog.records]
    assert any("run_loop.py" in msg for msg in messages)


def test_check_freshness_no_log_when_no_stale_files(workspace, caplog):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# old")
    old_mtime = time.time() - 120
    os.utime(py_file, (old_mtime, old_mtime))
    start_time = time.time() - 60
    with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.stale_bytecode_guard"):
        check_freshness(tmp_path, start_time)
    assert len(caplog.records) == 0


def test_check_freshness_log_contains_stale_bytecode_marker(workspace, caplog):
    tmp_path, orch_dir = workspace
    py_file = orch_dir / "parallel_loop.py"
    py_file.write_text("# parallel")
    start_time = time.time() - 60
    with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.stale_bytecode_guard"):
        check_freshness(tmp_path, start_time)
    messages = [r.getMessage() for r in caplog.records]
    assert any("STALE-BYTECODE" in msg for msg in messages)
