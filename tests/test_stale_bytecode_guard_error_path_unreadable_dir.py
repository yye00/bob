"""Tests that check_freshness raises PermissionError when orchestrator dir is unreadable."""

from __future__ import annotations

import os
import stat
import time
import pathlib

import pytest

from bob.orchestrator.stale_bytecode_guard import check_freshness


@pytest.fixture()
def workspace_with_locked_dir(tmp_path):
    """Create workspace with an unreadable orchestrator dir."""
    orch_dir = tmp_path / "src" / "bob" / "orchestrator"
    orch_dir.mkdir(parents=True)
    py_file = orch_dir / "run_loop.py"
    py_file.write_text("# code")
    return tmp_path, orch_dir, py_file


def test_check_freshness_raises_permission_error_on_unreadable_dir(workspace_with_locked_dir):
    """check_freshness raises PermissionError when orchestrator dir is chmod 000."""
    if os.getuid() == 0:
        pytest.skip("root ignores permission bits")

    tmp_path, orch_dir, py_file = workspace_with_locked_dir
    start_time = time.time() - 60

    orch_dir.chmod(0o000)
    try:
        with pytest.raises(PermissionError) as exc_info:
            check_freshness(tmp_path, start_time)
        assert "permission" in str(exc_info.value).lower()
    finally:
        orch_dir.chmod(0o755)


def test_check_freshness_permission_error_message_mentions_permission(workspace_with_locked_dir):
    """The PermissionError message contains 'permission' (case-insensitive)."""
    if os.getuid() == 0:
        pytest.skip("root ignores permission bits")

    tmp_path, orch_dir, py_file = workspace_with_locked_dir
    start_time = time.time() - 60

    orch_dir.chmod(0o000)
    try:
        raised = None
        try:
            check_freshness(tmp_path, start_time)
        except PermissionError as e:
            raised = e
        assert raised is not None, "Expected PermissionError was not raised"
        assert "permission" in str(raised).lower()
    finally:
        orch_dir.chmod(0o755)


def test_check_freshness_works_after_restoring_permissions(workspace_with_locked_dir):
    """After restoring dir permissions, check_freshness works normally."""
    if os.getuid() == 0:
        pytest.skip("root ignores permission bits")

    tmp_path, orch_dir, py_file = workspace_with_locked_dir
    start_time = time.time() - 60

    orch_dir.chmod(0o000)
    try:
        pass  # just testing the restore works
    finally:
        orch_dir.chmod(0o755)

    result = check_freshness(tmp_path, start_time)
    assert len(result) == 1
    assert result[0] == py_file
