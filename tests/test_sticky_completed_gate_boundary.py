"""Boundary-case tests for bob.sticky_gate.prevent_completed_regression.

Feature af9bdfc9 — AC: pytest: tests/test_sticky_completed_gate_boundary.py —
empty, zero, or minimum input returns a well-defined result rather than
raising (boundary case).
"""

from __future__ import annotations

import json

import pytest

from bob.sticky_gate import prevent_completed_regression as should_persist_completed_status


class TestBoundaryCases:
    """Empty / zero / minimum inputs must never raise — they return False."""

    def test_empty_json_list_string(self, tmp_path):
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria="[]",
            workspace=tmp_path,
        )
        assert result is False

    def test_empty_string_acceptance_criteria(self, tmp_path):
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria="",
            workspace=tmp_path,
        )
        assert result is False

    def test_whitespace_only_acceptance_criteria(self, tmp_path):
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria="   \n  ",
            workspace=tmp_path,
        )
        assert result is False

    def test_none_acceptance_criteria(self, tmp_path):
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=None,
            workspace=tmp_path,
        )
        assert result is False

    def test_empty_list_acceptance_criteria(self, tmp_path):
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=[],
            workspace=tmp_path,
        )
        assert result is False

    def test_parent_completed_false_minimum(self, tmp_path):
        """Minimum stamped=False: always returns False regardless of ACs."""
        result = should_persist_completed_status(
            parent_completed=False,
            target_status="failed",
            acceptance_criteria=None,
            workspace=tmp_path,
        )
        assert result is False

    def test_single_file_ac_file_missing(self, tmp_path):
        """Single AC referencing non-existent file — gate silent, returns False."""
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=json.dumps(["File exists: src/nope.py"]),
            workspace=tmp_path,
        )
        assert result is False

    def test_single_file_ac_file_present(self, tmp_path):
        """Minimum single-file AC that passes — gate fires, returns True."""
        target = tmp_path / "src" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("# x\n")
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=json.dumps(["File exists: src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is True

    def test_non_demoting_status_boundary(self, tmp_path):
        """Minimum case: stamped + ACs pass but target='ready' → gate silent."""
        target = tmp_path / "src" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("# x\n")
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="ready",
            acceptance_criteria=json.dumps(["File exists: src/mod.py"]),
            workspace=tmp_path,
        )
        assert result is False

    def test_acs_with_only_non_file_existence_criteria(self, tmp_path):
        """ACs without any file-existence entries → gate always silent."""
        acs = json.dumps([
            "pytest: tests/test_something.py",
            "Function defined: my.module.func",
            "integration: bob.evaluator",
        ])
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=acs,
            workspace=tmp_path,
        )
        assert result is False

    def test_workspace_as_string_path(self, tmp_path):
        """workspace may be passed as a str rather than pathlib.Path."""
        target = tmp_path / "x.py"
        target.write_text("# x\n")
        result = should_persist_completed_status(
            parent_completed=True,
            target_status="failed",
            acceptance_criteria=json.dumps(["File exists: x.py"]),
            workspace=str(tmp_path),
        )
        assert result is True
