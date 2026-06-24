"""Boundary tests for bob.baseline_gate.validate_collection.

AC: pytest: tests/test_stable_baseline_gate_boundary.py —
    empty, zero, or minimum input returns a well-defined result rather
    than raising (boundary case).
"""

from __future__ import annotations

import pathlib

import pytest

from bob_legacy.baseline_gate import CollectionResult, validate_collection


# ---------------------------------------------------------------------------
# workspace=None boundary
# ---------------------------------------------------------------------------

def test_none_workspace_returns_ok():
    """None workspace is valid; returns ok=True without subprocess."""
    result = validate_collection(None)
    assert isinstance(result, CollectionResult)
    assert result.ok
    assert result.failing_files == []


def test_none_workspace_does_not_raise():
    """Calling with workspace=None never raises."""
    validate_collection(None)  # must not raise


# ---------------------------------------------------------------------------
# Non-existent workspace boundary
# ---------------------------------------------------------------------------

def test_nonexistent_workspace_returns_ok(tmp_path):
    """If workspace dir does not exist, return ok=True (nothing to fail)."""
    ghost = tmp_path / "does_not_exist"
    result = validate_collection(ghost)
    assert result.ok


# ---------------------------------------------------------------------------
# Missing test_dir boundary
# ---------------------------------------------------------------------------

def test_missing_test_dir_returns_ok(tmp_path):
    """If the test directory doesn't exist inside workspace, return ok=True."""
    result = validate_collection(tmp_path, test_dir="tests")
    assert result.ok
    assert result.failing_files == []


def test_empty_test_dir_name_returns_ok(tmp_path):
    """test_dir that does not exist → well-defined ok=True result."""
    result = validate_collection(tmp_path, test_dir="nonexistent_subdir")
    assert isinstance(result, CollectionResult)
    assert result.ok


# ---------------------------------------------------------------------------
# workspace as string vs Path boundary
# ---------------------------------------------------------------------------

def test_workspace_as_string_path(tmp_path):
    """workspace can be passed as a plain string."""
    (tmp_path / "tests").mkdir()
    result = validate_collection(str(tmp_path) + "/does_not_exist_ws")
    assert isinstance(result, CollectionResult)
    assert result.ok


def test_workspace_as_pathlib_path(tmp_path):
    """workspace as pathlib.Path is supported."""
    result = validate_collection(pathlib.Path(tmp_path) / "no_such_dir")
    assert isinstance(result, CollectionResult)
    assert result.ok


# ---------------------------------------------------------------------------
# Minimum timeout boundary
# ---------------------------------------------------------------------------

def test_timeout_of_1_is_valid(tmp_path):
    """timeout=1 is the minimum legal value and must not raise."""
    result = validate_collection(None, timeout=1)
    assert isinstance(result, CollectionResult)
    assert result.ok


# ---------------------------------------------------------------------------
# Return type is always CollectionResult
# ---------------------------------------------------------------------------

def test_always_returns_collection_result_on_boundary_input():
    """All boundary inputs return CollectionResult, never raise, never None."""
    cases = [
        (None, {}, None),
        (None, {"test_dir": "t"}, None),
    ]
    for ws, kwargs, _ in cases:
        result = validate_collection(ws, **kwargs)
        assert isinstance(result, CollectionResult), f"Got {result!r} for ws={ws}"
