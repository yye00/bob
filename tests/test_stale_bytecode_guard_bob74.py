"""Tests for bob74.orchestrator.stale_bytecode_guard (feature 3d952825-b7f1-444f-9cdc-53db3cacba72).

Verifies that check_stale_bytecode correctly identifies orchestrator source files
that are newer than the recorded process start time.
"""

from __future__ import annotations

import logging
import os
import pathlib
import time

import pytest

from bob74.orchestrator.stale_bytecode_guard import check_stale_bytecode


@pytest.fixture()
def tmp_workspace(tmp_path):
    """Create a minimal workspace with an orchestrator src dir."""
    orch_dir = tmp_path / "src" / "bob74" / "orchestrator"
    orch_dir.mkdir(parents=True)
    return tmp_path, orch_dir


class TestCheckStaleBytecode:
    def test_returns_empty_when_no_src_dir(self, tmp_path):
        """workspace with no src/ dir returns []."""
        result = check_stale_bytecode(tmp_path, time.time())
        assert result == []

    def test_returns_empty_when_no_orch_dirs(self, tmp_path):
        """src/ exists but no bob*/orchestrator → returns []."""
        (tmp_path / "src").mkdir()
        result = check_stale_bytecode(tmp_path, time.time())
        assert result == []

    def test_returns_empty_when_all_files_older(self, tmp_workspace):
        """All files older than start_time → empty list."""
        workspace, orch_dir = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# old")
        old_mtime = time.time() - 60
        os.utime(py_file, (old_mtime, old_mtime))
        start_time = time.time() - 30
        result = check_stale_bytecode(workspace, start_time)
        assert result == []

    def test_detects_file_newer_than_start(self, tmp_workspace):
        """File written after process start → returned as stale."""
        workspace, orch_dir = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# new code")
        start_time = time.time() - 60
        result = check_stale_bytecode(workspace, start_time)
        assert len(result) == 1
        assert result[0] == py_file

    def test_returns_multiple_stale_files(self, tmp_workspace):
        """Multiple stale files are all returned."""
        workspace, orch_dir = tmp_workspace
        f1 = orch_dir / "a.py"
        f2 = orch_dir / "b.py"
        f1.write_text("# a")
        f2.write_text("# b")
        start_time = time.time() - 60
        result = check_stale_bytecode(workspace, start_time)
        assert set(result) == {f1, f2}

    def test_ignores_non_py_files(self, tmp_workspace):
        """Non-.py files are not returned."""
        workspace, orch_dir = tmp_workspace
        (orch_dir / "README.txt").write_text("docs")
        (orch_dir / "run_loop.pyc").write_bytes(b"\x00\x01")
        start_time = time.time() - 60
        result = check_stale_bytecode(workspace, start_time)
        assert result == []

    def test_scans_multiple_bob_dirs(self, tmp_path):
        """src/bob3/orchestrator and src/bob74/orchestrator both scanned."""
        for gen in ("bob3", "bob74"):
            d = tmp_path / "src" / gen / "orchestrator"
            d.mkdir(parents=True)
            (d / "run_loop.py").write_text("# code")
        start_time = time.time() - 60
        result = check_stale_bytecode(tmp_path, start_time)
        assert len(result) == 2

    def test_logs_warning_for_stale_file(self, tmp_workspace, caplog):
        """A WARNING log is emitted for each stale file."""
        workspace, orch_dir = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# stale")
        start_time = time.time() - 60
        with caplog.at_level(logging.WARNING, logger="bob74.orchestrator.stale_bytecode_guard"):
            check_stale_bytecode(workspace, start_time)
        assert any("run_loop.py" in r.message for r in caplog.records)

    def test_returns_list_type_always(self, tmp_path):
        """Return type is always list."""
        result = check_stale_bytecode(tmp_path, time.time())
        assert isinstance(result, list)
