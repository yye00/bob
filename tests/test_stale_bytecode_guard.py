"""Tests for stale-bytecode guard (feature 67a3cb40-85aa-40eb-a26f-6d150ee0d298).

Verifies that check_freshness correctly identifies orchestrator source files
that are newer than the recorded process start time, and that record_start_time
persists the start time into .bob.lock.
"""

from __future__ import annotations

import json
import os
import pathlib
import time

import pytest

from bob.orchestrator.stale_bytecode_guard import (
    check_freshness,
    guard_relaunch_on_stale_bytecode,
    orchestrator_sources_changed_since,
    record_start_time,
)


@pytest.fixture()
def tmp_workspace(tmp_path):
    """Create a minimal workspace with an orchestrator src dir."""
    orch_dir = tmp_path / "src" / "bob" / "orchestrator"
    orch_dir.mkdir(parents=True)
    lock_file = tmp_path / ".bob.lock"
    return tmp_path, orch_dir, lock_file


class TestRecordStartTime:
    def test_creates_lock_file_with_started_at(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        record_start_time(lock_file, pid=12345)
        assert lock_file.exists()

    def test_lock_file_contains_pid(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        record_start_time(lock_file, pid=12345)
        data = json.loads(lock_file.read_text())
        assert data["pid"] == 12345

    def test_lock_file_contains_started_at(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        t_before = time.time()
        record_start_time(lock_file, pid=99)
        t_after = time.time()
        data = json.loads(lock_file.read_text())
        assert "started_at" in data
        started = data["started_at"]
        assert t_before <= started <= t_after

    def test_overwrites_existing_lock_file(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        lock_file.write_text("99999")  # old plain-PID format
        record_start_time(lock_file, pid=42)
        data = json.loads(lock_file.read_text())
        assert data["pid"] == 42

    def test_uses_current_pid_by_default(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        record_start_time(lock_file)
        data = json.loads(lock_file.read_text())
        assert data["pid"] == os.getpid()


class TestCheckFreshness:
    def test_returns_empty_when_no_orch_dirs(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        orch_dir.rmdir()
        start_time = time.time() + 10  # far future
        result = check_freshness(workspace, start_time)
        assert result == []

    def test_returns_empty_when_all_files_older(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# old")
        # Set mtime to 60s in the past
        old_mtime = time.time() - 60
        os.utime(py_file, (old_mtime, old_mtime))
        start_time = time.time() - 30  # process started 30s ago
        result = check_freshness(workspace, start_time)
        assert result == []

    def test_detects_file_newer_than_start(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# new code")
        # File written now, process started 60s ago
        start_time = time.time() - 60
        result = check_freshness(workspace, start_time)
        assert len(result) == 1
        assert result[0] == py_file

    def test_returns_multiple_stale_files(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        f1 = orch_dir / "a.py"
        f2 = orch_dir / "b.py"
        f1.write_text("# a")
        f2.write_text("# b")
        start_time = time.time() - 60
        result = check_freshness(workspace, start_time)
        assert set(result) == {f1, f2}

    def test_ignores_non_py_files(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        txt_file = orch_dir / "README.txt"
        txt_file.write_text("docs")
        start_time = time.time() - 60
        result = check_freshness(workspace, start_time)
        assert result == []

    def test_scans_multiple_bob_dirs(self, tmp_path):
        """src/bob/orchestrator and src/bob4/orchestrator both scanned."""
        for gen in ("bob", "bob4"):
            d = tmp_path / "src" / gen / "orchestrator"
            d.mkdir(parents=True)
            (d / "run_loop.py").write_text("# code")
        start_time = time.time() - 60
        result = check_freshness(tmp_path, start_time)
        assert len(result) == 2

    def test_start_time_from_lock_file(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# new")
        # Write lock file with a start_time 60s ago
        started_at = time.time() - 60
        lock_file.write_text(json.dumps({"pid": 1234, "started_at": started_at}))
        # check_freshness should accept a lock_file Path and extract started_at
        result = check_freshness(workspace, lock_file=lock_file)
        assert len(result) == 1

    def test_returns_empty_for_old_plain_pid_lock(self, tmp_workspace):
        """Old-format lock file (plain PID int) falls back to proc/stat mtime."""
        workspace, orch_dir, lock_file = tmp_workspace
        old_mtime = time.time() - 60
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# old file")
        os.utime(py_file, (old_mtime, old_mtime))
        lock_file.write_text("1234")  # plain-PID old format
        # No start_time kwarg, old lock format → falls back; file is older so no stale files
        result = check_freshness(workspace, lock_file=lock_file)
        assert result == []

    def test_check_freshness_logs_stale_file(self, tmp_workspace, caplog):
        import logging
        workspace, orch_dir, lock_file = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# stale")
        start_time = time.time() - 60
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.stale_bytecode_guard"):
            check_freshness(workspace, start_time)
        assert any("run_loop.py" in r.message for r in caplog.records)


class TestOrchestratorSourcesChangedSince:
    def test_true_when_file_newer_than_start(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        (orch_dir / "run_loop.py").write_text("# new code")
        start_time = time.time() - 60
        assert orchestrator_sources_changed_since(workspace, start_time) is True

    def test_false_when_all_files_older(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# old")
        old_mtime = time.time() - 60
        os.utime(py_file, (old_mtime, old_mtime))
        start_time = time.time() - 30
        assert orchestrator_sources_changed_since(workspace, start_time) is False

    def test_false_when_no_orch_dir(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        orch_dir.rmdir()
        assert orchestrator_sources_changed_since(workspace, time.time()) is False

    def test_returns_bool_type(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        result = orchestrator_sources_changed_since(workspace, time.time())
        assert isinstance(result, bool)

    def test_resolves_start_time_from_lock_file(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        (orch_dir / "run_loop.py").write_text("# new")
        lock_file.write_text(json.dumps({"pid": 1, "started_at": time.time() - 60}))
        assert orchestrator_sources_changed_since(workspace, lock_file=lock_file) is True

    def test_invalid_workspace_raises_value_error(self):
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            orchestrator_sources_changed_since("/some/path", time.time())

    def test_no_start_time_and_no_lock_raises_value_error(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        with pytest.raises(ValueError):
            orchestrator_sources_changed_since(workspace)


class TestGuardRelaunchOnStaleBytecode:
    def test_no_relaunch_when_not_stale(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        py_file = orch_dir / "run_loop.py"
        py_file.write_text("# old")
        old_mtime = time.time() - 60
        os.utime(py_file, (old_mtime, old_mtime))
        called = []
        result = guard_relaunch_on_stale_bytecode(
            workspace,
            start_time=time.time() - 30,
            relaunch=lambda: called.append(True),
        )
        assert result is False
        assert called == []

    def test_relaunch_invoked_when_stale(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        (orch_dir / "run_loop.py").write_text("# new code")
        called = []
        result = guard_relaunch_on_stale_bytecode(
            workspace,
            start_time=time.time() - 60,
            relaunch=lambda: called.append(True),
        )
        assert result is True
        assert called == [True]

    def test_returns_bool(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        result = guard_relaunch_on_stale_bytecode(
            workspace, start_time=time.time(), relaunch=lambda: None
        )
        assert isinstance(result, bool)

    def test_resolves_start_time_from_lock_file(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        (orch_dir / "run_loop.py").write_text("# new")
        lock_file.write_text(json.dumps({"pid": 1, "started_at": time.time() - 60}))
        called = []
        result = guard_relaunch_on_stale_bytecode(
            workspace, lock_file=lock_file, relaunch=lambda: called.append(True)
        )
        assert result is True
        assert called == [True]

    def test_invalid_workspace_raises_value_error(self):
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            guard_relaunch_on_stale_bytecode("/x", start_time=time.time())

    def test_non_callable_relaunch_raises_value_error(self, tmp_workspace):
        workspace, orch_dir, lock_file = tmp_workspace
        with pytest.raises(ValueError, match="relaunch must be callable"):
            guard_relaunch_on_stale_bytecode(
                workspace, start_time=time.time(), relaunch="not-callable"
            )

    def test_logs_warning_when_relaunching(self, tmp_workspace, caplog):
        import logging
        workspace, orch_dir, lock_file = tmp_workspace
        (orch_dir / "run_loop.py").write_text("# new")
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.stale_bytecode_guard"):
            guard_relaunch_on_stale_bytecode(
                workspace, start_time=time.time() - 60, relaunch=lambda: None
            )
        assert any("relaunch" in r.message.lower() for r in caplog.records)
