"""Boundary tests for check_stale_bytecode (feature d2df584f-9b5a-4279-9a2c-d712609fe474).

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import pathlib
import time

import pytest

from bob_orchestrator.stale_bytecode_guard import check_stale_bytecode


@pytest.fixture()
def empty_workspace(tmp_path):
    """A workspace with no src/ directory at all."""
    return tmp_path


@pytest.fixture()
def workspace_no_orch(tmp_path):
    """A workspace with src/ but no bob*/orchestrator directories."""
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture()
def workspace_empty_orch(tmp_path):
    """A workspace with an empty orchestrator directory."""
    orch = tmp_path / "src" / "bob3" / "orchestrator"
    orch.mkdir(parents=True)
    return tmp_path


class TestBoundaryEmptyInput:
    def test_no_src_dir_returns_empty_list(self, empty_workspace):
        """workspace with no src/ dir returns [] without raising."""
        result = check_stale_bytecode(empty_workspace, time.time())
        assert result == []

    def test_src_dir_no_bob_dirs_returns_empty_list(self, workspace_no_orch):
        """src/ exists but no bob*/orchestrator → returns []."""
        result = check_stale_bytecode(workspace_no_orch, time.time())
        assert result == []

    def test_empty_orchestrator_dir_returns_empty_list(self, workspace_empty_orch):
        """orchestrator dir exists but is empty → returns []."""
        result = check_stale_bytecode(workspace_empty_orch, time.time())
        assert result == []

    def test_start_time_zero_returns_list_not_raises(self, workspace_empty_orch):
        """start_time=0 (epoch) is valid — all files are newer, no exception raised."""
        orch = workspace_empty_orch / "src" / "bob3" / "orchestrator"
        py_file = orch / "run_loop.py"
        py_file.write_text("# code")
        result = check_stale_bytecode(workspace_empty_orch, 0.0)
        # All files newer than epoch 0 → at least the one we wrote is stale
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_very_large_start_time_returns_empty_list(self, workspace_empty_orch):
        """start_time far in the future → no files are stale → returns []."""
        orch = workspace_empty_orch / "src" / "bob3" / "orchestrator"
        py_file = orch / "run_loop.py"
        py_file.write_text("# code")
        far_future = time.time() + 1_000_000
        result = check_stale_bytecode(workspace_empty_orch, far_future)
        assert result == []

    def test_only_non_py_files_returns_empty_list(self, workspace_empty_orch):
        """orchestrator dir with only .pyc and .txt files → [] (only .py checked)."""
        orch = workspace_empty_orch / "src" / "bob3" / "orchestrator"
        (orch / "run_loop.pyc").write_bytes(b"\x00\x01\x02")
        (orch / "README.txt").write_text("docs")
        result = check_stale_bytecode(workspace_empty_orch, 0.0)
        assert result == []

    def test_returns_list_type_always(self, empty_workspace):
        """Return type is always list, never None."""
        result = check_stale_bytecode(empty_workspace, time.time())
        assert isinstance(result, list)
