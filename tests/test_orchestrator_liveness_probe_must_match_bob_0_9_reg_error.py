"""Error-path tests for orchestrator liveness probe.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (error path AC).

Tests lock_holder_pid_alive and check_lock_file_holder with invalid
(non-path-like) inputs to confirm ValueError is raised rather than
swallowed or returning a meaningless value.
"""

from __future__ import annotations

import pytest

from bob3.liveness import check_lock_file_holder, validate_lock_file_holder
from bob3.orchestrator.liveness_probe import lock_holder_pid_alive


# ---------------------------------------------------------------------------
# lock_holder_pid_alive — invalid (non-path-like) input raises ValueError
# ---------------------------------------------------------------------------


def test_lock_holder_pid_alive_raises_on_int():
    """lock_holder_pid_alive raises ValueError when given an int, not a path."""
    with pytest.raises(ValueError, match="lock_path must be a str"):
        lock_holder_pid_alive(12345)


def test_lock_holder_pid_alive_raises_on_list():
    """lock_holder_pid_alive raises ValueError when given a list."""
    with pytest.raises(ValueError):
        lock_holder_pid_alive(["/some/path"])


def test_lock_holder_pid_alive_raises_on_dict():
    """lock_holder_pid_alive raises ValueError when given a dict."""
    with pytest.raises(ValueError):
        lock_holder_pid_alive({"path": "/some/path"})


def test_lock_holder_pid_alive_raises_on_none():
    """lock_holder_pid_alive raises ValueError when given None."""
    with pytest.raises(ValueError):
        lock_holder_pid_alive(None)


def test_lock_holder_pid_alive_raises_on_float():
    """lock_holder_pid_alive raises ValueError when given a float."""
    with pytest.raises(ValueError):
        lock_holder_pid_alive(3.14)


def test_lock_holder_pid_alive_error_is_not_silent():
    """lock_holder_pid_alive must raise, not return False, for a non-path-like int.

    Confirms the function does not silently succeed (return False) when given
    invalid input — the caller must receive an exception, not a quietly
    wrong result that hides the programming error.
    """
    try:
        result = lock_holder_pid_alive(42)
        # If we reach here, the function swallowed the error — test must fail.
        pytest.fail(
            f"lock_holder_pid_alive(42) returned {result!r} instead of raising ValueError"
        )
    except ValueError:
        pass  # expected


# ---------------------------------------------------------------------------
# check_lock_file_holder (liveness public API) — mirrors same contract
# ---------------------------------------------------------------------------


def test_check_lock_file_holder_raises_on_int():
    """check_lock_file_holder raises ValueError when given an int."""
    with pytest.raises(ValueError):
        check_lock_file_holder(12345)


def test_check_lock_file_holder_raises_on_none():
    """check_lock_file_holder raises ValueError when given None."""
    with pytest.raises(ValueError):
        check_lock_file_holder(None)


def test_validate_lock_file_holder_raises_on_list():
    """validate_lock_file_holder (alias) raises ValueError when given a list."""
    with pytest.raises(ValueError):
        validate_lock_file_holder(["/some/path"])
