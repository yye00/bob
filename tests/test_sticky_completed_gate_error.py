"""Error-path tests for bob3.sticky_gate.prevent_completed_regression.

Feature af9bdfc9 — AC: pytest: tests/test_sticky_completed_gate_error.py —
invalid input raises ValueError and the function does not silently succeed
(error path).
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.sticky_gate import prevent_completed_regression as should_persist_completed_status


class TestInvalidParentCompleted:
    """Non-bool parent_completed must raise ValueError."""

    def test_parent_completed_none_raises(self, tmp_path):
        with pytest.raises(ValueError, match="parent_completed"):
            should_persist_completed_status(
                parent_completed=None,  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=tmp_path,
            )

    def test_parent_completed_int_raises(self, tmp_path):
        with pytest.raises(ValueError, match="parent_completed"):
            should_persist_completed_status(
                parent_completed=1,  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=tmp_path,
            )

    def test_parent_completed_string_raises(self, tmp_path):
        with pytest.raises(ValueError, match="parent_completed"):
            should_persist_completed_status(
                parent_completed="true",  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=tmp_path,
            )

    def test_parent_completed_list_raises(self, tmp_path):
        with pytest.raises(ValueError, match="parent_completed"):
            should_persist_completed_status(
                parent_completed=[],  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=tmp_path,
            )


class TestInvalidTargetStatus:
    """Non-string or empty target_status must raise ValueError."""

    def test_target_status_none_raises(self, tmp_path):
        with pytest.raises(ValueError, match="target_status"):
            should_persist_completed_status(
                parent_completed=True,
                target_status=None,  # type: ignore[arg-type]
                acceptance_criteria=None,
                workspace=tmp_path,
            )

    def test_target_status_empty_raises(self, tmp_path):
        with pytest.raises(ValueError, match="target_status"):
            should_persist_completed_status(
                parent_completed=True,
                target_status="",
                acceptance_criteria=None,
                workspace=tmp_path,
            )

    def test_target_status_whitespace_only_raises(self, tmp_path):
        with pytest.raises(ValueError, match="target_status"):
            should_persist_completed_status(
                parent_completed=True,
                target_status="   ",
                acceptance_criteria=None,
                workspace=tmp_path,
            )

    def test_target_status_int_raises(self, tmp_path):
        with pytest.raises(ValueError, match="target_status"):
            should_persist_completed_status(
                parent_completed=True,
                target_status=42,  # type: ignore[arg-type]
                acceptance_criteria=None,
                workspace=tmp_path,
            )


class TestInvalidWorkspace:
    """Non-existent or non-directory workspace must raise ValueError."""

    def test_nonexistent_workspace_raises(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        with pytest.raises(ValueError, match="workspace"):
            should_persist_completed_status(
                parent_completed=True,
                target_status="failed",
                acceptance_criteria=None,
                workspace=missing,
            )

    def test_file_as_workspace_raises(self, tmp_path):
        a_file = tmp_path / "not_a_dir.txt"
        a_file.write_text("data")
        with pytest.raises(ValueError, match="workspace"):
            should_persist_completed_status(
                parent_completed=True,
                target_status="failed",
                acceptance_criteria=None,
                workspace=a_file,
            )


class TestNoSilentSuccess:
    """Ensure invalid inputs do not produce a True return (silent success)."""

    def test_invalid_parent_completed_does_not_return_true(self, tmp_path):
        """The function must raise, never silently return True."""
        raised = False
        try:
            result = should_persist_completed_status(
                parent_completed="yes",  # type: ignore[arg-type]
                target_status="failed",
                acceptance_criteria=None,
                workspace=tmp_path,
            )
            # If we reach here (no exception), result must not be True.
            assert result is not True, (
                "Function silently returned True for invalid parent_completed"
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError was not raised for invalid parent_completed"

    def test_invalid_target_status_does_not_return_true(self, tmp_path):
        raised = False
        try:
            result = should_persist_completed_status(
                parent_completed=True,
                target_status="",
                acceptance_criteria=None,
                workspace=tmp_path,
            )
            assert result is not True, (
                "Function silently returned True for empty target_status"
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError was not raised for empty target_status"
