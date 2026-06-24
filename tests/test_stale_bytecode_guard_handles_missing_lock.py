"""Tests for handle_missing_lock_file and check_freshness in stale_bytecode_guard."""

from __future__ import annotations

import json
import pathlib
import time

import pytest

from bob.orchestrator.stale_bytecode_guard import check_freshness, handle_missing_lock_file


def test_handle_missing_lock_file_returns_true_when_absent(tmp_path: pathlib.Path) -> None:
    """handle_missing_lock_file returns True (conservative stale) when lock file does not exist."""
    lock_file = tmp_path / ".bob.lock"
    assert not lock_file.exists(), "precondition: lock file must not exist"
    result = handle_missing_lock_file(lock_file)
    assert result is True, f"expected True when lock file absent, got {result!r}"


def test_handle_missing_lock_file_returns_false_when_present(tmp_path: pathlib.Path) -> None:
    """handle_missing_lock_file returns False when lock file exists."""
    lock_file = tmp_path / ".bob.lock"
    lock_file.write_text(json.dumps({"pid": 1234, "started_at": time.time()}))
    assert lock_file.exists(), "precondition: lock file must exist"
    result = handle_missing_lock_file(lock_file)
    assert result is False, f"expected False when lock file present, got {result!r}"


def test_handle_missing_lock_file_returns_false_for_empty_file(tmp_path: pathlib.Path) -> None:
    """handle_missing_lock_file returns False for an empty lock file (exists, but no content)."""
    lock_file = tmp_path / ".bob.lock"
    lock_file.write_text("")  # exists but empty
    result = handle_missing_lock_file(lock_file)
    assert result is False, "expected False when lock file exists even if empty"


def test_check_freshness_returns_empty_list_when_lock_file_missing(tmp_path: pathlib.Path) -> None:
    """check_freshness returns [] when lock_file kwarg points to a non-existent file.

    _read_start_time_from_lock catches the OSError and returns None; a None
    start_time from a missing or old plain-PID lock triggers an early return of [].
    """
    workspace = tmp_path / "workspace"
    (workspace / "src" / "bob" / "orchestrator").mkdir(parents=True)
    lock_file = workspace / ".bob.lock"
    assert not lock_file.exists(), "precondition: lock file must not exist"

    result = check_freshness(workspace, lock_file=lock_file)
    assert result == [], f"expected [] when lock file absent, got {result!r}"


def test_check_freshness_raises_value_error_without_args(tmp_path: pathlib.Path) -> None:
    """check_freshness raises ValueError when neither start_time nor lock_file is provided."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ValueError):
        check_freshness(workspace)


def test_handle_missing_lock_file_nested_nonexistent_path(tmp_path: pathlib.Path) -> None:
    """handle_missing_lock_file returns True for a lock file inside a non-existent subdirectory."""
    lock_file = tmp_path / "deep" / "nested" / ".bob.lock"
    assert not lock_file.exists(), "precondition: nested lock file must not exist"
    result = handle_missing_lock_file(lock_file)
    assert result is True, "expected True when the entire path hierarchy is absent"
