"""Error-path tests for validate_regression_ownership (feature 22356d3b-f0c3-408f-9dd8-23ad03333e43).

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (error path).
"""

from __future__ import annotations

import pytest

from bob3.regression_detection import validate_regression_ownership


def test_empty_feature_id_raises_valueerror():
    """Empty string feature_id must raise ValueError."""
    with pytest.raises(ValueError, match="feature_id"):
        validate_regression_ownership(
            feature_id="",
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )


def test_none_feature_id_raises_valueerror():
    """None feature_id must raise ValueError."""
    with pytest.raises(ValueError):
        validate_regression_ownership(
            feature_id=None,
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )


def test_list_owned_files_raises_valueerror():
    """Passing a list as owned_files must raise ValueError, not silently succeed."""
    with pytest.raises(ValueError, match="owned_files"):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files=["src/foo.py"],
            breaking_files={"src/foo.py"},
        )


def test_tuple_owned_files_raises_valueerror():
    """Passing a tuple as owned_files must raise ValueError."""
    with pytest.raises(ValueError, match="owned_files"):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files=("src/foo.py",),
            breaking_files={"src/foo.py"},
        )


def test_list_breaking_files_raises_valueerror():
    """Passing a list as breaking_files must raise ValueError."""
    with pytest.raises(ValueError, match="breaking_files"):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files={"src/foo.py"},
            breaking_files=["src/foo.py"],
        )


def test_tuple_breaking_files_raises_valueerror():
    """Passing a tuple as breaking_files must raise ValueError."""
    with pytest.raises(ValueError, match="breaking_files"):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files={"src/foo.py"},
            breaking_files=("src/foo.py",),
        )


def test_whitespace_only_feature_id_raises_valueerror():
    """A feature_id of only whitespace must be rejected."""
    with pytest.raises(ValueError, match="feature_id"):
        validate_regression_ownership(
            feature_id="   ",
            owned_files={"src/foo.py"},
            breaking_files={"src/foo.py"},
        )


def test_dict_owned_files_raises_valueerror():
    """Passing a dict as owned_files must raise ValueError."""
    with pytest.raises(ValueError, match="owned_files"):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files={"src/foo.py": True},
            breaking_files={"src/foo.py"},
        )


def test_none_owned_files_raises_valueerror():
    """None for owned_files must raise ValueError (not AttributeError or silent pass)."""
    with pytest.raises((ValueError, TypeError)):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files=None,
            breaking_files={"src/foo.py"},
        )


def test_none_breaking_files_raises_valueerror():
    """None for breaking_files must raise ValueError (not AttributeError or silent pass)."""
    with pytest.raises((ValueError, TypeError)):
        validate_regression_ownership(
            feature_id="feat-error",
            owned_files={"src/foo.py"},
            breaking_files=None,
        )
