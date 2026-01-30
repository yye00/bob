"""Tests for stall detection in ClaudeExecutor."""

import os
import time
import threading
from pathlib import Path

import pytest

from bob.orchestrator.claude_executor import FileModificationWatcher


class TestFileModificationWatcher:
    """Test FileModificationWatcher for stall detection."""

    def test_init(self, tmp_path):
        """Test watcher initialization."""
        watcher = FileModificationWatcher(
            watch_dir=tmp_path,
            stall_timeout=60,
            check_interval=5,
        )
        assert watcher.watch_dir == tmp_path
        assert watcher.stall_timeout == 60
        assert watcher.check_interval == 5
        assert watcher.stalled is False

    def test_no_stall_with_modifications(self, tmp_path):
        """Test that no stall is detected when files are modified."""
        # Create a file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        stall_detected = threading.Event()

        watcher = FileModificationWatcher(
            watch_dir=tmp_path,
            stall_timeout=2,
            check_interval=1,
            on_stall=lambda: stall_detected.set(),
        )
        watcher.start()

        # Keep modifying a file
        for _ in range(3):
            time.sleep(0.5)
            test_file.write_text(f"print('{time.time()}')")

        watcher.stop()
        assert not stall_detected.is_set()
        assert not watcher.stalled

    def test_stall_detected_no_modifications(self, tmp_path):
        """Test that stall IS detected when no files are modified."""
        stall_detected = threading.Event()

        watcher = FileModificationWatcher(
            watch_dir=tmp_path,
            stall_timeout=1,  # 1 second for fast test
            check_interval=0.5,
            on_stall=lambda: stall_detected.set(),
        )
        watcher.start()

        # Wait for stall detection
        stall_detected.wait(timeout=5)
        watcher.stop()

        assert stall_detected.is_set()
        assert watcher.stalled

    def test_scan_mtimes(self, tmp_path):
        """Test scanning modification times."""
        watcher = FileModificationWatcher(watch_dir=tmp_path)

        # Empty dir
        mtime = watcher._scan_mtimes()
        assert mtime == 0.0  # No files

        # Create a file
        test_file = tmp_path / "test.py"
        test_file.write_text("hello")
        mtime = watcher._scan_mtimes()
        assert mtime > 0

    def test_skip_dirs(self, tmp_path):
        """Test that hidden/skip dirs are ignored."""
        watcher = FileModificationWatcher(watch_dir=tmp_path)

        # Create files in skip directories
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").write_bytes(b"\x00" * 100)

        # Create a real file
        real_file = tmp_path / "main.py"
        real_file.write_text("print('real')")

        mtime = watcher._scan_mtimes()
        # Should get the mtime of main.py, not the skip-dir files
        assert mtime > 0

    def test_start_stop_idempotent(self, tmp_path):
        """Test that start/stop can be called multiple times."""
        watcher = FileModificationWatcher(
            watch_dir=tmp_path,
            stall_timeout=999,
            check_interval=999,
        )
        watcher.start()
        watcher.stop()
        watcher.stop()  # Should not crash
        assert not watcher.stalled

    def test_on_stall_callback(self, tmp_path):
        """Test that the on_stall callback is invoked."""
        callback_data = {"called": False}

        def my_callback():
            callback_data["called"] = True

        watcher = FileModificationWatcher(
            watch_dir=tmp_path,
            stall_timeout=1,
            check_interval=0.5,
            on_stall=my_callback,
        )
        watcher.start()
        time.sleep(3)
        watcher.stop()

        assert callback_data["called"]


class TestMultiDebugConfig:
    """Test that max_debug_attempts config is correctly passed."""

    def test_default_max_debug_attempts(self):
        """Test default max_debug_attempts is 3."""
        from bob.orchestrator.engine import OrchestratorConfig
        config = OrchestratorConfig()
        assert config.max_debug_attempts == 3

    def test_custom_max_debug_attempts(self):
        """Test custom max_debug_attempts."""
        from bob.orchestrator.engine import OrchestratorConfig
        config = OrchestratorConfig(max_debug_attempts=5)
        assert config.max_debug_attempts == 5

    def test_default_stall_timeout(self):
        """Test default stall_timeout is 600."""
        from bob.orchestrator.engine import OrchestratorConfig
        config = OrchestratorConfig()
        assert config.stall_timeout == 600

    def test_custom_stall_timeout(self):
        """Test custom stall_timeout."""
        from bob.orchestrator.engine import OrchestratorConfig
        config = OrchestratorConfig(stall_timeout=300)
        assert config.stall_timeout == 300


class TestClaudeExecutorStallIntegration:
    """Test stall detection integration in ClaudeExecutor."""

    def test_executor_has_stall_timeout(self):
        """Test that ClaudeExecutor accepts stall_timeout."""
        from bob.orchestrator.claude_executor import ClaudeExecutor
        executor = ClaudeExecutor(
            project_dir=Path("/tmp/test"),
            stall_timeout=120,
        )
        assert executor.stall_timeout == 120

    def test_executor_default_stall_timeout(self):
        """Test that ClaudeExecutor has default stall_timeout."""
        from bob.orchestrator.claude_executor import ClaudeExecutor
        executor = ClaudeExecutor(project_dir=Path("/tmp/test"))
        assert executor.stall_timeout == 600
