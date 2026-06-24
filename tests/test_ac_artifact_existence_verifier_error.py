"""Error-path tests for ac_verifier.verify_artifacts.

Invalid input must raise ValueError; the function must not silently succeed.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ac_verifier import verify_artifacts


def test_non_list_acs_raises_value_error():
    """Passing a non-list for acs (e.g. a plain string) must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        verify_artifacts("File exists: foo.py", workspace="/tmp")  # type: ignore[arg-type]


def test_none_acs_raises():
    """Passing None for acs must raise (TypeError or ValueError)."""
    with pytest.raises((ValueError, TypeError)):
        verify_artifacts(None, workspace="/tmp")  # type: ignore[arg-type]


def test_none_workspace_raises():
    """Passing None for workspace must raise (TypeError or ValueError)."""
    with pytest.raises((ValueError, TypeError, AttributeError)):
        verify_artifacts([], workspace=None)  # type: ignore[arg-type]


def test_path_traversal_ac_is_rejected_or_flagged():
    """An AC with a path-traversal component must not silently succeed (no real file read)."""
    result = verify_artifacts(["File exists: ../../etc/passwd"], workspace="/tmp")
    # Must either be flagged as a miss OR raise — it must not return empty (success)
    assert isinstance(result, list)
    # Path traversal cannot be treated as a passing AC
    assert len(result) >= 1, (
        "Path traversal AC should not silently pass; expected at least one miss"
    )


def test_absolute_path_in_ac_is_rejected_or_flagged():
    """An AC with an absolute path must not silently succeed."""
    result = verify_artifacts(["File exists: /etc/passwd"], workspace="/tmp")
    assert isinstance(result, list)
    # Must not silently pass — absolute paths escape the workspace confinement
    assert len(result) >= 1, (
        "Absolute path AC should not silently pass; expected at least one miss"
    )


def test_integer_in_ac_list_raises():
    """A list containing a non-string item (int) must raise."""
    with pytest.raises((ValueError, TypeError, AttributeError)):
        verify_artifacts([42], workspace="/tmp")  # type: ignore[list-item]
