"""Error-path tests for disk_state_reconciler.reconcile_from_disk (feature 91320c77).

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from disk_state_reconciler import reconcile_from_disk


def test_empty_project_id_raises_value_error(tmp_path):
    """reconcile_from_disk('') raises ValueError."""
    with pytest.raises(ValueError, match="project_id"):
        reconcile_from_disk("", workspace=tmp_path)


def test_none_project_id_raises_value_error(tmp_path):
    """reconcile_from_disk(None) raises ValueError."""
    with pytest.raises(ValueError):
        reconcile_from_disk(None, workspace=tmp_path)


def test_whitespace_project_id_raises_value_error(tmp_path):
    """reconcile_from_disk with whitespace-only project_id raises ValueError."""
    with pytest.raises(ValueError, match="project_id"):
        reconcile_from_disk("   ", workspace=tmp_path)


def test_error_message_mentions_project_id(tmp_path):
    """The ValueError message explicitly contains 'project_id'."""
    try:
        reconcile_from_disk("", workspace=tmp_path)
        pytest.fail("Expected ValueError was not raised")
    except ValueError as exc:
        assert "project_id" in str(exc), (
            f"ValueError message must mention 'project_id', got: {exc!r}"
        )


def test_invalid_project_id_does_not_silently_succeed(tmp_path):
    """reconcile_from_disk with invalid project_id does NOT return 0 or succeed silently."""
    try:
        result = reconcile_from_disk("", workspace=tmp_path)
        pytest.fail(f"Expected ValueError but got result: {result}")
    except ValueError:
        pass  # expected
