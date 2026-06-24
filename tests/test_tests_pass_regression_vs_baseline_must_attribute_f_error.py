"""Error-path tests for bob.regression_attribution.attribute_test_failure_to_owner.

AC: pytest: tests/test_tests_pass_regression_vs_baseline_must_attribute_f_error.py —
    invalid input raises ValueError and the function does not silently succeed
    (error path).

Feature 656281e3-1c55-4a5d-be92-21163a281bf8
"""

from __future__ import annotations

import pytest

from bob.regression_attribution import attribute_test_failure_to_owner


# ---------------------------------------------------------------------------
# Error: non-string test_path raises ValueError
# ---------------------------------------------------------------------------

def test_none_test_path_raises_value_error():
    """None is not a valid test_path — must raise ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner(None)


def test_integer_test_path_raises_value_error():
    """An integer test_path raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner(42)


def test_list_test_path_raises_value_error():
    """A list test_path raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner(["tests/test_foo.py"])


def test_dict_test_path_raises_value_error():
    """A dict test_path raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner({"path": "tests/test_foo.py"})


def test_bool_test_path_raises_value_error():
    """bool (True/False) as test_path raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner(True)


def test_bytes_test_path_raises_value_error():
    """bytes test_path raises ValueError — must be a str."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner(b"tests/test_foo.py")


# ---------------------------------------------------------------------------
# Error: empty string test_path raises ValueError
# ---------------------------------------------------------------------------

def test_empty_string_test_path_raises_value_error():
    """An empty string is not a valid test path — raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner("")


def test_whitespace_only_test_path_raises_value_error():
    """A whitespace-only string is not a valid test path — raises ValueError."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner("   ")


def test_newline_only_test_path_raises_value_error():
    """A newline-only string raises ValueError (treated as empty/blank)."""
    with pytest.raises(ValueError):
        attribute_test_failure_to_owner("\n")


# ---------------------------------------------------------------------------
# Error: errors are not silently swallowed
# ---------------------------------------------------------------------------

def test_none_path_error_not_silently_swallowed():
    """ValueError from None test_path must propagate — not be caught internally."""
    result = None
    exc = None
    try:
        result = attribute_test_failure_to_owner(None)
    except ValueError as e:
        exc = e
    assert exc is not None, "ValueError should have been raised"
    assert result is None, "No result should be returned on error"


def test_empty_path_error_not_silently_swallowed():
    """ValueError from empty test_path must propagate — not be caught internally."""
    result = None
    exc = None
    try:
        result = attribute_test_failure_to_owner("")
    except ValueError as e:
        exc = e
    assert exc is not None, "ValueError should have been raised"
    assert result is None, "No result should be returned on error"


def test_integer_path_error_not_silently_swallowed():
    """ValueError from integer test_path must propagate — not be caught internally."""
    result = None
    exc = None
    try:
        result = attribute_test_failure_to_owner(0)
    except ValueError as e:
        exc = e
    assert exc is not None, "ValueError should have been raised"
    assert result is None, "No result should be returned on error"


# ---------------------------------------------------------------------------
# Error: ValueError message is informative (contains 'test_path')
# ---------------------------------------------------------------------------

def test_value_error_message_mentions_test_path():
    """The raised ValueError message should mention 'test_path' for clarity."""
    with pytest.raises(ValueError, match="test_path"):
        attribute_test_failure_to_owner(None)


def test_value_error_for_empty_string_mentions_test_path():
    """ValueError for empty string mentions 'test_path'."""
    with pytest.raises(ValueError, match="test_path"):
        attribute_test_failure_to_owner("")
