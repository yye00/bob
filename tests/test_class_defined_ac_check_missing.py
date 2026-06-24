"""Tests for check_class_defined_ac when class is absent."""

import pathlib
import pytest
from bob.verification.class_defined_ac_check import check_class_defined_ac


def test_returns_false_when_class_not_present(tmp_path):
    """check_class_defined_ac returns False when class not present anywhere in workspace."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "example.py").write_text("class OtherClass:\n    pass\n")
    result = check_class_defined_ac("MissingClass", tmp_path)
    assert result is False


def test_returns_false_for_empty_workspace(tmp_path):
    """Empty workspace has no classes at all."""
    result = check_class_defined_ac("AnyClass", tmp_path)
    assert result is False


def test_does_not_match_class_name_as_substring(tmp_path):
    """'Report' should not match 'MutationReport' — exact class name required."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "example.py").write_text("class MutationReport:\n    pass\n")
    result = check_class_defined_ac("Report", tmp_path)
    assert result is False


def test_returns_false_for_nonexistent_workspace():
    """Graceful failure when workspace does not exist."""
    result = check_class_defined_ac("SomeClass", pathlib.Path("/nonexistent/path/xyz"))
    assert result is False


def test_does_not_match_variable_named_same_as_class(tmp_path):
    """An assignment 'MutationReport = ...' should NOT be confused with a class definition."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "example.py").write_text("MutationReport = None\n")
    result = check_class_defined_ac("MutationReport", tmp_path)
    assert result is False
