"""Tests for bob.orchestrator.stale_bytecode.should_relaunch_on_stale_bytecode.

Feature: Stale-bytecode guard at relaunch (fd401bd3-2afa-4eee-b67d-6af7449dfaac)

Self-heal compares mtime of every file under src/bob*/orchestrator/ against
the previous bob_N process's start time. If any orchestrator source file is
newer than process start, kill+relaunch even when the DB looks recoverable.
"""

from __future__ import annotations

import math
import os
import pathlib
import time

import pytest

from bob.orchestrator.stale_bytecode import should_relaunch_on_stale_bytecode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_workspace(tmp_path):
    """Workspace with no src/ directory."""
    return tmp_path


@pytest.fixture()
def workspace_no_orch(tmp_path):
    """Workspace with src/ but no bob*/orchestrator directories."""
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture()
def workspace_with_orch(tmp_path):
    """Workspace with a properly structured bob/orchestrator directory."""
    orch = tmp_path / "src" / "bob" / "orchestrator"
    orch.mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestShouldRelaunchHappyPath:
    def test_returns_false_when_no_src_dir(self, empty_workspace):
        """No src/ → no stale files → returns False."""
        result = should_relaunch_on_stale_bytecode(empty_workspace, time.time())
        assert result is False

    def test_returns_false_when_no_orchestrator_dirs(self, workspace_no_orch):
        """src/ exists but no bob*/orchestrator → returns False."""
        result = should_relaunch_on_stale_bytecode(workspace_no_orch, time.time())
        assert result is False

    def test_returns_false_when_all_files_older_than_start_time(self, workspace_with_orch):
        """Files exist but are older than start_time → returns False."""
        orch = workspace_with_orch / "src" / "bob" / "orchestrator"
        py_file = orch / "run_loop.py"
        py_file.write_text("# old code")
        # Use a future start_time so all files appear older
        far_future = time.time() + 1_000_000
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, far_future)
        assert result is False

    def test_returns_true_when_file_newer_than_start_time(self, workspace_with_orch):
        """File mtime > start_time → returns True (stale bytecode detected)."""
        orch = workspace_with_orch / "src" / "bob" / "orchestrator"
        py_file = orch / "run_loop.py"
        py_file.write_text("# new code")
        # Use epoch as start_time so any real file is newer
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, 0.0)
        assert result is True

    def test_returns_false_when_only_non_py_files_exist(self, workspace_with_orch):
        """Only .pyc/.txt files in orchestrator → returns False (.py only scanned)."""
        orch = workspace_with_orch / "src" / "bob" / "orchestrator"
        (orch / "run_loop.pyc").write_bytes(b"\x00\x01\x02")
        (orch / "README.txt").write_text("docs")
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, 0.0)
        assert result is False

    def test_returns_true_on_first_stale_file_found(self, workspace_with_orch):
        """Returns True as soon as first stale file is detected (short-circuit)."""
        orch = workspace_with_orch / "src" / "bob" / "orchestrator"
        for i in range(5):
            (orch / f"module_{i}.py").write_text(f"# module {i}")
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, 0.0)
        assert result is True

    def test_scans_multiple_bob_generation_dirs(self, tmp_path):
        """Files from multiple bob*/orchestrator dirs are all checked."""
        for gen in ("bob", "bob4", "bob5"):
            orch = tmp_path / "src" / gen / "orchestrator"
            orch.mkdir(parents=True)
            (orch / "run_loop.py").write_text(f"# {gen}")

        far_future = time.time() + 1_000_000
        result = should_relaunch_on_stale_bytecode(tmp_path, far_future)
        assert result is False

        result_stale = should_relaunch_on_stale_bytecode(tmp_path, 0.0)
        assert result_stale is True

    def test_returns_bool_not_truthy(self, workspace_with_orch):
        """Return value is exactly bool True or False, not a list or int."""
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, time.time())
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


class TestShouldRelaunchErrorPath:
    def test_raises_value_error_for_string_workspace(self, tmp_path):
        """workspace as str raises ValueError."""
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            should_relaunch_on_stale_bytecode("/some/path", time.time())

    def test_raises_value_error_for_int_workspace(self):
        """workspace as int raises ValueError."""
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            should_relaunch_on_stale_bytecode(42, time.time())

    def test_raises_value_error_for_string_start_time(self, tmp_path):
        """process_start_time as str raises ValueError."""
        with pytest.raises(ValueError, match="process_start_time must be a numeric type"):
            should_relaunch_on_stale_bytecode(tmp_path, "2026-01-01")

    def test_raises_value_error_for_nan_start_time(self, tmp_path):
        """process_start_time=nan raises ValueError."""
        with pytest.raises(ValueError, match="process_start_time must be a finite number"):
            should_relaunch_on_stale_bytecode(tmp_path, math.nan)

    def test_raises_value_error_for_inf_start_time(self, tmp_path):
        """process_start_time=inf raises ValueError."""
        with pytest.raises(ValueError, match="process_start_time must be a finite number"):
            should_relaunch_on_stale_bytecode(tmp_path, math.inf)

    def test_raises_value_error_for_neg_inf_start_time(self, tmp_path):
        """process_start_time=-inf raises ValueError."""
        with pytest.raises(ValueError, match="process_start_time must be a finite number"):
            should_relaunch_on_stale_bytecode(tmp_path, -math.inf)


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------


class TestShouldRelaunchBoundary:
    def test_start_time_zero_treats_all_files_as_stale(self, workspace_with_orch):
        """start_time=0.0 (epoch) → all files created after epoch are stale."""
        orch = workspace_with_orch / "src" / "bob" / "orchestrator"
        (orch / "run_loop.py").write_text("# code")
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, 0.0)
        assert result is True

    def test_empty_orchestrator_dir_returns_false(self, workspace_with_orch):
        """orchestrator dir exists but is empty → returns False."""
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, 0.0)
        assert result is False

    def test_int_start_time_is_accepted(self, workspace_with_orch):
        """int start_time (not just float) is accepted without raising."""
        result = should_relaunch_on_stale_bytecode(workspace_with_orch, 0)
        assert isinstance(result, bool)
