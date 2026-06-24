"""Error path tests for get_scoped_pytest_command in bob.superpowers.

Feature: 40799127-8e65-4c47-b671-0bbc6aa9ce66
AC: pytest: tests/test_subagent_self_verification_must_use_scoped_pytest__error.py

Tests that invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.superpowers import get_scoped_pytest_command


class TestGetScopedPytestCommandErrorPath:
    """Error path: invalid inputs raise ValueError; no silent success."""

    def test_non_list_non_none_raises_value_error(self):
        """Passing a non-list, non-None value raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command("tests/test_foo.py")

    def test_integer_input_raises_value_error(self):
        """Passing an integer raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command(42)

    def test_dict_input_raises_value_error(self):
        """Passing a dict raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command({"pytest": "tests/test_foo.py"})

    def test_bool_true_raises_value_error(self):
        """Passing True raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command(True)

    def test_bool_false_raises_value_error(self):
        """Passing False raises ValueError (booleans are not valid acceptance criteria)."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command(False)

    def test_tuple_input_raises_value_error(self):
        """Passing a tuple (not a list) raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command(("pytest: tests/test_foo.py",))

    def test_non_string_list_item_raises_value_error(self):
        """A list containing a non-string item raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command([123, "pytest: tests/test_foo.py"])

    def test_nested_list_raises_value_error(self):
        """A list containing a nested list raises ValueError."""
        with pytest.raises(ValueError):
            get_scoped_pytest_command([["pytest: tests/test_foo.py"]])

    def test_error_message_mentions_acceptance_criteria(self):
        """ValueError message must mention what was expected (acceptance_criteria or list)."""
        with pytest.raises(ValueError, match=r"(?i)acceptance.criteria|list"):
            get_scoped_pytest_command("bad_input")
