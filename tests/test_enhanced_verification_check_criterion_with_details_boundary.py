"""Boundary tests for _check_criterion_with_details — F-R7-576.

Verifies that empty, zero-length, or minimum-content inputs return a
well-defined result rather than raising any exception.
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.enhanced_verification import _check_criterion_with_details


def _call(criterion: str, tmp_path: pathlib.Path) -> tuple[bool, str]:
    return _check_criterion_with_details(
        criterion=criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestEmptyAndMinimumInputs:
    """Boundary: empty, whitespace-only, and single-character inputs."""

    def test_empty_string_does_not_raise(self, tmp_path):
        result = _call("", tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 2
        passed, details = result
        assert isinstance(passed, bool)
        assert isinstance(details, str)

    def test_whitespace_only_does_not_raise(self, tmp_path):
        result = _call("   ", tmp_path)
        assert isinstance(result, tuple)
        passed, details = result
        assert isinstance(passed, bool)

    def test_single_word_does_not_raise(self, tmp_path):
        result = _call("x", tmp_path)
        assert isinstance(result, tuple)
        passed, details = result
        assert isinstance(passed, bool)

    def test_newline_only_does_not_raise(self, tmp_path):
        result = _call("\n", tmp_path)
        assert isinstance(result, tuple)
        passed, details = result
        assert isinstance(passed, bool)

    def test_minimum_prose_criterion_returns_bool(self, tmp_path):
        """A minimal non-structural string returns a bool, not an exception."""
        result = _call("must do something", tmp_path)
        assert isinstance(result, tuple)
        passed, details = result
        assert isinstance(passed, bool)
        assert isinstance(details, str)

    def test_minimum_structural_criterion_returns_bool(self, tmp_path):
        """'File exists:' with no filename is still well-defined (False, not raise)."""
        result = _call("File exists:", tmp_path)
        assert isinstance(result, tuple)
        passed, details = result
        assert isinstance(passed, bool)

    def test_pytest_prefix_with_empty_body(self, tmp_path):
        """'pytest:' with no test path returns a defined result."""
        result = _call("pytest:", tmp_path)
        assert isinstance(result, tuple)
        passed, details = result
        assert isinstance(passed, bool)
