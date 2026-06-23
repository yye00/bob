"""Error-path tests for handle_structural_log_line in bob3.enhanced_verification.

Verifies that invalid (non-string criterion_body or non-Path workspace) inputs
raise ValueError and the function does not silently succeed.

AC: "pytest: tests/test_structural_log_line_ac_handler_error.py — invalid input
raises ValueError and the function does not silently succeed (error path)"
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.enhanced_verification import handle_structural_log_line


class TestInvalidCriterionBodyType:
    """Non-string criterion_body must raise ValueError immediately."""

    def test_none_criterion_body_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            handle_structural_log_line(criterion_body=None, workspace=tmp_path)

    def test_int_criterion_body_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            handle_structural_log_line(criterion_body=42, workspace=tmp_path)

    def test_bytes_criterion_body_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            handle_structural_log_line(
                criterion_body=b"src/bob3/foo.py emits a 'x' log line",
                workspace=tmp_path,
            )

    def test_list_criterion_body_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            handle_structural_log_line(criterion_body=[], workspace=tmp_path)

    def test_dict_criterion_body_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            handle_structural_log_line(criterion_body={}, workspace=tmp_path)


class TestInvalidWorkspaceType:
    """Non-Path workspace must raise ValueError immediately."""

    def test_none_workspace_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            handle_structural_log_line(
                criterion_body="src/bob3/foo.py emits a 'x' log line",
                workspace=None,
            )

    def test_string_workspace_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            handle_structural_log_line(
                criterion_body="src/bob3/foo.py emits a 'x' log line",
                workspace=str(tmp_path),
            )

    def test_int_workspace_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            handle_structural_log_line(
                criterion_body="src/bob3/foo.py emits a 'x' log line",
                workspace=0,
            )


class TestDoesNotSilentlySucceedOnInvalidInput:
    """Confirm the function never returns True or None silently on bad input."""

    def test_none_criterion_does_not_return_true(self, tmp_path):
        """None criterion must NOT silently return True (the pass result)."""
        with pytest.raises(ValueError):
            result = handle_structural_log_line(
                criterion_body=None, workspace=tmp_path
            )
            # Should never reach here — but if it does, ensure it's not True
            assert result is not True

    def test_none_workspace_does_not_return_true(self, tmp_path):
        """None workspace must NOT silently return True."""
        with pytest.raises(ValueError):
            result = handle_structural_log_line(
                criterion_body="a.py emits a 'x' log line", workspace=None
            )
            assert result is not True
