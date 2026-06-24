"""Boundary/edge-case tests for orchestrator liveness probe.

Verifies that empty, zero, or minimum inputs return a well-defined result
rather than raising (boundary case AC).

Tests check_orchestrator_running, check_lock_file_holder, and verify_db_activity
with edge-case inputs: empty process list, empty lock file, zero PID, etc.
"""

from __future__ import annotations

import os
import pathlib
from unittest.mock import patch

import pytest

from bob.liveness import (
    check_lock_file_holder,
    check_orchestrator_running,
    validate_lock_file_holder,
    verify_db_activity,
)


# ---------------------------------------------------------------------------
# check_orchestrator_running — no input, always returns bool
# ---------------------------------------------------------------------------

def test_check_orchestrator_running_empty_process_list():
    """check_orchestrator_running with no processes returns False without raising."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[],
    ):
        result = check_orchestrator_running()
    assert result is False
    assert isinstance(result, bool)


def test_check_orchestrator_running_single_non_matching_process():
    """check_orchestrator_running with one non-matching process returns False."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[(1, "init")],
    ):
        result = check_orchestrator_running()
    assert result is False
    assert isinstance(result, bool)


def test_check_orchestrator_running_returns_bool():
    """check_orchestrator_running always returns a bool, never a truthy non-bool."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[],
    ):
        result = check_orchestrator_running()
    assert type(result) is bool


def test_check_orchestrator_running_with_single_matching_process():
    """check_orchestrator_running with minimum one matching process returns True."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[(99001, "bob run")],
    ):
        result = check_orchestrator_running()
    assert result is True
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# check_lock_file_holder — boundary inputs: empty string path, empty file, zero PID
# ---------------------------------------------------------------------------

def test_check_lock_file_holder_nonexistent_path(tmp_path):
    """check_lock_file_holder on a missing lock file returns False without raising."""
    missing = tmp_path / "nonexistent.lock"
    result = check_lock_file_holder(missing)
    assert result is False
    assert isinstance(result, bool)


def test_check_lock_file_holder_empty_file(tmp_path):
    """check_lock_file_holder on an empty lock file returns False without raising."""
    lock = tmp_path / ".bob.lock"
    lock.write_text("", encoding="utf-8")
    result = check_lock_file_holder(lock)
    assert result is False
    assert isinstance(result, bool)


def test_check_lock_file_holder_zero_pid(tmp_path):
    """check_lock_file_holder on a lock file with PID=0 returns False without raising."""
    lock = tmp_path / ".bob.lock"
    lock.write_text("0\n", encoding="utf-8")
    result = check_lock_file_holder(lock)
    assert result is False
    assert isinstance(result, bool)


def test_check_lock_file_holder_whitespace_only_file(tmp_path):
    """check_lock_file_holder on a whitespace-only lock file returns False."""
    lock = tmp_path / ".bob.lock"
    lock.write_text("   \n\t\n", encoding="utf-8")
    result = check_lock_file_holder(lock)
    assert result is False
    assert isinstance(result, bool)


def test_check_lock_file_holder_empty_string_path():
    """check_lock_file_holder with empty string path returns False without raising."""
    result = check_lock_file_holder("")
    assert result is False
    assert isinstance(result, bool)


def test_check_lock_file_holder_min_valid_path(tmp_path):
    """check_lock_file_holder with the current process PID returns True (minimum live PID)."""
    lock = tmp_path / ".bob.lock"
    lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
    result = check_lock_file_holder(lock)
    assert result is True
    assert isinstance(result, bool)


def test_validate_lock_file_holder_empty_file_is_false(tmp_path):
    """validate_lock_file_holder (alias) returns False for empty file without raising."""
    lock = tmp_path / ".bob.lock"
    lock.write_text("", encoding="utf-8")
    result = validate_lock_file_holder(lock)
    assert result is False
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# verify_db_activity — boundary: None db_path, error-free call
# ---------------------------------------------------------------------------

def test_verify_db_activity_no_args_returns_bool():
    """verify_db_activity() with no arguments returns a bool without raising."""
    with patch(
        "bob.orchestrator.liveness_probe._has_recent_executing_rows",
        return_value=False,
    ):
        result = verify_db_activity()
    assert isinstance(result, bool)
    assert result is False


def test_verify_db_activity_none_db_path_returns_bool():
    """verify_db_activity(db_path=None) returns a bool without raising."""
    with patch(
        "bob.orchestrator.liveness_probe._has_recent_executing_rows",
        return_value=False,
    ):
        result = verify_db_activity(db_path=None)
    assert isinstance(result, bool)


def test_verify_db_activity_returns_true_on_exception():
    """verify_db_activity returns True (conservative) when DB raises, not an exception."""
    with patch(
        "bob.orchestrator.liveness_probe._has_recent_executing_rows",
        side_effect=RuntimeError("DB unavailable"),
    ):
        result = verify_db_activity()
    assert result is True
    assert isinstance(result, bool)
