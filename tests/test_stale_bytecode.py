"""Tests for bob3.stale_bytecode.check_stale_bytecode (feature 0769add9-d0b4-4f81-853e-d0037104d8d0).

Self-heal compares mtime of every file under src/bob*/orchestrator/ against the
previous bob_N process's start time. If any orchestrator source file is newer
than process start, kill+relaunch the process even when the DB looks recoverable.
"""

from __future__ import annotations

import math
import pathlib
import time

import pytest

from bob3.stale_bytecode import check_stale_bytecode


class TestCheckStaleBytecodeBasic:
    def test_returns_empty_list_when_no_src_dir(self, tmp_path):
        """No src/ directory → empty list, no exception."""
        result = check_stale_bytecode(tmp_path, time.time())
        assert result == []

    def test_returns_empty_list_when_no_bob_dirs(self, tmp_path):
        """src/ exists but no bob*/orchestrator dirs → empty list."""
        (tmp_path / "src").mkdir()
        result = check_stale_bytecode(tmp_path, time.time())
        assert result == []

    def test_returns_empty_list_when_no_py_files(self, tmp_path):
        """Orchestrator dir exists but has no .py files → empty list."""
        orch = tmp_path / "src" / "bob3" / "orchestrator"
        orch.mkdir(parents=True)
        (orch / "README.txt").write_text("docs")
        result = check_stale_bytecode(tmp_path, time.time())
        assert result == []

    def test_detects_newer_py_file(self, tmp_path):
        """A .py file newer than start_time is returned as stale."""
        orch = tmp_path / "src" / "bob3" / "orchestrator"
        orch.mkdir(parents=True)
        py_file = orch / "run_loop.py"
        py_file.write_text("# code")
        # start_time in the past → file is stale
        result = check_stale_bytecode(tmp_path, 0.0)
        assert py_file in result

    def test_does_not_return_older_py_file(self, tmp_path):
        """A .py file older than start_time is NOT returned."""
        orch = tmp_path / "src" / "bob3" / "orchestrator"
        orch.mkdir(parents=True)
        py_file = orch / "run_loop.py"
        py_file.write_text("# code")
        # start_time far in the future → file is NOT stale
        result = check_stale_bytecode(tmp_path, time.time() + 1_000_000)
        assert result == []

    def test_skips_non_py_files(self, tmp_path):
        """Only .py files are checked; .pyc and .txt are ignored."""
        orch = tmp_path / "src" / "bob3" / "orchestrator"
        orch.mkdir(parents=True)
        (orch / "run_loop.pyc").write_bytes(b"\x00\x01\x02")
        (orch / "notes.txt").write_text("ignore")
        result = check_stale_bytecode(tmp_path, 0.0)
        assert result == []

    def test_returns_list_type(self, tmp_path):
        """Return type is always list, never None."""
        result = check_stale_bytecode(tmp_path, time.time())
        assert isinstance(result, list)

    def test_scans_multiple_bob_dirs(self, tmp_path):
        """Files from multiple src/bob*/orchestrator dirs are all checked."""
        for bob_dir in ("bob3", "bob72"):
            orch = tmp_path / "src" / bob_dir / "orchestrator"
            orch.mkdir(parents=True)
            (orch / "run_loop.py").write_text("# code")
        result = check_stale_bytecode(tmp_path, 0.0)
        assert len(result) == 2


class TestCheckStaleBytecodeValidation:
    def test_non_path_workspace_raises_value_error(self, tmp_path):
        """workspace as string raises ValueError."""
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            check_stale_bytecode("/tmp/workspace", time.time())  # type: ignore[arg-type]

    def test_workspace_as_int_raises_value_error(self, tmp_path):
        """workspace as int raises ValueError."""
        with pytest.raises(ValueError, match="workspace must be a pathlib.Path"):
            check_stale_bytecode(42, time.time())  # type: ignore[arg-type]

    def test_start_time_as_string_raises_value_error(self, tmp_path):
        """start_time as str raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a numeric type"):
            check_stale_bytecode(tmp_path, "2026-01-01")  # type: ignore[arg-type]

    def test_start_time_nan_raises_value_error(self, tmp_path):
        """start_time=float('nan') raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a finite number"):
            check_stale_bytecode(tmp_path, math.nan)

    def test_start_time_inf_raises_value_error(self, tmp_path):
        """start_time=float('inf') raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a finite number"):
            check_stale_bytecode(tmp_path, math.inf)

    def test_start_time_neg_inf_raises_value_error(self, tmp_path):
        """start_time=-float('inf') raises ValueError."""
        with pytest.raises(ValueError, match="start_time must be a finite number"):
            check_stale_bytecode(tmp_path, -math.inf)
