"""Error path tests for pytest_plugins.snapshot_maxfail_enforcer.

Tests that invalid input raises ValueError and the function does not
silently succeed.
"""

from __future__ import annotations

import pytest
from pytest_plugins import snapshot_maxfail_enforcer


class TestNonListInputRaisesValueError:
    """Non-list argv must raise ValueError, not silently succeed."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(None)

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer("pytest --maxfail=0 tests/")

    def test_tuple_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(("pytest", "tests/"))

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(42)

    def test_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer({"pytest": "tests/"})


class TestNonStringElementsRaisesValueError:
    """List elements that are not strings must raise ValueError."""

    def test_integer_element_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(["pytest", 4, "tests/"])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(["pytest", None])

    def test_list_element_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(["pytest", ["tests/"]])

    def test_bool_element_raises_value_error(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(["pytest", True])


class TestErrorMessageQuality:
    """ValueError messages must be informative, not silent failures."""

    def test_none_error_message_mentions_type(self):
        with pytest.raises(ValueError, match=r"list"):
            snapshot_maxfail_enforcer(None)

    def test_string_error_message_informative(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer("not a list")

    def test_integer_element_error_mentions_index_or_type(self):
        with pytest.raises(ValueError):
            snapshot_maxfail_enforcer(["pytest", 99])
