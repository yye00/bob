"""Boundary tests for bob3.acceptance_criteria.verify_artifact_existence (FC56E557).

Empty, zero, or minimum input must return a well-defined result rather than raising.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob3.acceptance_criteria import verify_artifact_existence


def test_empty_list_returns_empty():
    """Empty AC list must return an empty list, not raise."""
    result = verify_artifact_existence([], workspace="/tmp")
    assert result == []


def test_single_empty_string_ac():
    """A single empty-string AC must return a well-defined result, not raise."""
    result = verify_artifact_existence([""], workspace="/tmp")
    assert isinstance(result, list)


def test_whitespace_only_ac():
    """A whitespace-only AC must return a well-defined result, not raise."""
    result = verify_artifact_existence(["   "], workspace="/tmp")
    assert isinstance(result, list)


def test_single_passing_ac_no_exception():
    """A single recognized and satisfied AC must not raise."""
    ws = Path(tempfile.mkdtemp())
    (ws / "exists.py").write_text("# ok")
    result = verify_artifact_existence(["File exists: exists.py"], workspace=ws)
    assert isinstance(result, list)
    assert result == []


def test_single_failing_ac_no_exception():
    """A single failing AC must not raise; it must return a list with one miss."""
    result = verify_artifact_existence(["File exists: definitely_gone.py"], workspace="/tmp")
    assert isinstance(result, list)
    assert len(result) >= 1


def test_single_pytest_ac_empty_path():
    """pytest: with an empty path after the prefix must return a miss, not raise."""
    result = verify_artifact_existence(["pytest:"], workspace="/tmp")
    assert isinstance(result, list)


def test_many_empty_string_acs():
    """A list of only empty strings must return a well-defined list, not raise."""
    result = verify_artifact_existence(["", "", ""], workspace="/tmp")
    assert isinstance(result, list)


def test_unknown_prefix_ac_boundary():
    """An unrecognized prefix must produce a well-defined miss, not raise."""
    result = verify_artifact_existence(["some_unknown_prefix: value"], workspace="/tmp")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0].kind == "unknown_prefix"


def test_workspace_as_string_boundary():
    """workspace passed as a string instead of Path must work, not raise."""
    result = verify_artifact_existence([], workspace="/tmp")
    assert isinstance(result, list)
