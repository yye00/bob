"""Tests for error path: reconcile_from_disk with invalid project_id."""

from __future__ import annotations

import pytest

from bob.orchestrator.disk_reconciler import reconcile_from_disk


def test_reconcile_raises_value_error_for_none_project_id(tmp_path):
    """reconcile_from_disk(None) raises ValueError with 'project_id' in message."""
    with pytest.raises(ValueError, match="project_id"):
        reconcile_from_disk(None, workspace=tmp_path)


def test_reconcile_raises_value_error_for_empty_string_project_id(tmp_path):
    """reconcile_from_disk('') raises ValueError with 'project_id' in message."""
    with pytest.raises(ValueError, match="project_id"):
        reconcile_from_disk("", workspace=tmp_path)


def test_reconcile_raises_value_error_message_mentions_project_id_for_none(tmp_path):
    """The ValueError message explicitly contains the word 'project_id'."""
    try:
        reconcile_from_disk(None, workspace=tmp_path)
        pytest.fail("Expected ValueError not raised")
    except ValueError as exc:
        assert "project_id" in str(exc), (
            f"ValueError message must mention 'project_id', got: {exc}"
        )
