"""Boundary tests for handle_structural_log_line in bob3.enhanced_verification.

Verifies that empty, zero-length, and minimum valid inputs return a well-defined
result (True or None) rather than raising an exception.

AC: "pytest: tests/test_structural_log_line_ac_handler_boundary.py — empty, zero,
or minimum input returns a well-defined result rather than raising (boundary case)"
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.enhanced_verification import handle_structural_log_line


def _call(criterion_body: str, workspace: pathlib.Path) -> bool | None:
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )


class TestEmptyAndMinimumInput:
    """Empty, zero-length, and minimum valid criterion_body never raise."""

    def test_empty_criterion_body_returns_none(self, tmp_path):
        """Empty string does not match the emits pattern — returns None, no raise."""
        result = _call("", tmp_path)
        assert result is None

    def test_whitespace_only_criterion_returns_none(self, tmp_path):
        """Whitespace-only string does not match — returns None, no raise."""
        result = _call("   \t\n  ", tmp_path)
        assert result is None

    def test_single_char_criterion_returns_none(self, tmp_path):
        """Single character — does not match emits pattern — returns None."""
        result = _call("x", tmp_path)
        assert result is None

    def test_minimum_matching_criterion_with_empty_log_string(self, tmp_path):
        """Criterion matches regex but log string is empty after strip — None (no raise)."""
        # Regex requires at least one char in the quoted group, so this should
        # not match and should return None without raising.
        result = _call("foo.py emits a '' log line", tmp_path)
        assert result is None

    def test_emits_pattern_but_missing_file_returns_none(self, tmp_path):
        """Minimum valid criterion with file absent returns None, no raise."""
        result = _call("a.py emits a 'x' log line", tmp_path)
        assert result is None

    def test_minimum_valid_match_file_exists_with_string(self, tmp_path):
        """Minimum valid criterion: single-token log string found in file → True."""
        py_file = tmp_path / "a.py"
        py_file.write_text('logger.info("x")\n')
        result = _call("a.py emits a 'x' log line", tmp_path)
        assert result is True

    def test_minimum_valid_match_file_exists_string_absent(self, tmp_path):
        """Minimum valid criterion: single-token log string absent in file → None."""
        py_file = tmp_path / "a.py"
        py_file.write_text('logger.info("y")\n')
        result = _call("a.py emits a 'x' log line", tmp_path)
        assert result is None

    def test_zero_byte_source_file_returns_none(self, tmp_path):
        """Source file exists but is zero bytes — log string not found → None."""
        py_file = tmp_path / "a.py"
        py_file.write_text("")
        result = _call("a.py emits a 'x' log line", tmp_path)
        assert result is None

    def test_criterion_with_only_py_path_no_emits_returns_none(self, tmp_path):
        """Criterion has .py path but no 'emits' — returns None."""
        result = _call("src/bob3/foo.py defines function bar", tmp_path)
        assert result is None

    def test_criterion_emits_but_no_quoted_string_returns_none(self, tmp_path):
        """'emits' present but no quoted string — regex won't match → None."""
        result = _call("src/bob3/foo.py emits a log line", tmp_path)
        assert result is None
