"""Error-path tests for ensure_tests_package.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (error path AC).
"""

from __future__ import annotations

import pytest

from bob.skeleton_tests_package import ensure_tests_package


def test_none_root_raises_value_error():
    """Passing None for project_root raises ValueError."""
    with pytest.raises(ValueError, match="must not be None"):
        ensure_tests_package(None)


def test_empty_string_root_raises_value_error():
    """Passing an empty string raises ValueError."""
    with pytest.raises(ValueError, match="empty string"):
        ensure_tests_package("")


def test_whitespace_string_root_raises_value_error():
    """Passing a whitespace-only string raises ValueError."""
    with pytest.raises(ValueError, match="empty string"):
        ensure_tests_package("   ")


def test_non_path_type_raises_value_error():
    """Passing a non-str/Path type raises ValueError naming the type."""
    with pytest.raises(ValueError, match="int"):
        ensure_tests_package(42)


def test_nonexistent_root_raises_value_error():
    """Pointing at a path that does not exist raises ValueError."""
    with pytest.raises(ValueError, match="does not exist"):
        ensure_tests_package("/no/such/path/for/skeleton/xyz")


def test_file_as_root_raises_value_error(tmp_path):
    """Passing a file (not a directory) as project_root raises ValueError."""
    a_file = tmp_path / "afile.txt"
    a_file.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        ensure_tests_package(a_file)


def test_valid_root_does_not_raise(tmp_path):
    """A valid directory root does not raise and returns a result."""
    (tmp_path / "tests").mkdir()
    result = ensure_tests_package(tmp_path)
    assert result is not None
