"""BF-4 error-path tests: invalid input raises ValueError and does not silently succeed.

These tests verify that bob3.brownfield.localizer and the BF-4 entry-point
raise ValueError (not swallowing errors) when given clearly invalid input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bob3.brownfield.localizer import localize
from bob3.bf_4_hierarchical_localizer_file_class_symbol_edit_site import (
    bf_4_hierarchical_localizer_file_class_symbol_edit_site,
)


# ---------------------------------------------------------------------------
# Invalid intent type — entry-point must raise ValueError
# ---------------------------------------------------------------------------

def test_entry_point_string_intent_raises() -> None:
    """String intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent="add auth")


def test_entry_point_list_intent_raises() -> None:
    """List intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=["auth", "login"])


def test_entry_point_int_intent_raises() -> None:
    """Integer intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=42)


def test_entry_point_float_intent_raises() -> None:
    """Float intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=3.14)


def test_entry_point_bool_intent_raises() -> None:
    """Boolean intent raises ValueError (bool is not a dict)."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=True)


def test_entry_point_tuple_intent_raises() -> None:
    """Tuple intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=("auth", "login"))


def test_entry_point_set_intent_raises() -> None:
    """Set intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent={"auth", "login"})


# ---------------------------------------------------------------------------
# Verify error is raised not silently swallowed
# ---------------------------------------------------------------------------

def test_string_intent_does_not_return_empty_silently() -> None:
    """Verify string intent raises rather than returning an empty result dict."""
    try:
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent="oops")
        # If we reach here, it didn't raise — this is a failure
        pytest.fail(
            f"Expected ValueError for string intent, but got result: {result!r}"
        )
    except ValueError:
        pass  # Correct: ValueError was raised


def test_list_intent_does_not_return_silently() -> None:
    """List intent raises — not a silent empty return."""
    try:
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=[])
        pytest.fail(f"Expected ValueError for list intent, got: {result!r}")
    except ValueError:
        pass


def test_int_intent_does_not_return_silently() -> None:
    """Integer intent raises — not a silent empty return."""
    try:
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=0)
        pytest.fail(f"Expected ValueError for int intent 0, got: {result!r}")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Error messages are informative (ValueError carries the bad type name)
# ---------------------------------------------------------------------------

def test_value_error_message_mentions_type() -> None:
    """ValueError for invalid intent type should mention the actual type."""
    with pytest.raises(ValueError, match="str"):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent="bad")


def test_value_error_message_mentions_list_type() -> None:
    """ValueError for list intent should mention 'list'."""
    with pytest.raises(ValueError, match="list"):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=["a"])


def test_value_error_message_mentions_int_type() -> None:
    """ValueError for int intent should mention 'int'."""
    with pytest.raises(ValueError, match="int"):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=99)


# ---------------------------------------------------------------------------
# Valid dict intents must NOT raise (ensures no over-triggering)
# ---------------------------------------------------------------------------

def test_valid_dict_intent_does_not_raise() -> None:
    """Valid dict intent with no survey_db must not raise ValueError."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
        intent={"capability": "add login", "keywords": ["auth"]}
    )
    assert isinstance(result, dict)


def test_empty_dict_intent_does_not_raise() -> None:
    """Empty dict intent must not raise ValueError."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent={})
    assert isinstance(result, dict)


def test_none_intent_does_not_raise() -> None:
    """None intent must not raise ValueError (treated as empty intent)."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=None)
    assert isinstance(result, dict)
