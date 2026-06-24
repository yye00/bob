"""Error-path tests for verify_quoted_substring_ac.

AC: pytest: tests/test_behavior_ac_quoted_substring_must_mention_must_not_error.py
    — invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pathlib

import pytest

from bob.enhanced_verification import verify_quoted_substring_ac


# ---------------------------------------------------------------------------
# verify_quoted_substring_ac — invalid input must raise ValueError
# ---------------------------------------------------------------------------

def test_none_criterion_raises_value_error(tmp_path):
    """None criterion must raise ValueError, not return None silently."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(None, tmp_path)


def test_integer_criterion_raises_value_error(tmp_path):
    """Integer criterion must raise ValueError."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(42, tmp_path)


def test_zero_criterion_raises_value_error(tmp_path):
    """Zero (int) criterion must raise ValueError."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(0, tmp_path)


def test_float_criterion_raises_value_error(tmp_path):
    """Float criterion must raise ValueError."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(3.14, tmp_path)


def test_list_criterion_raises_value_error(tmp_path):
    """List criterion must raise ValueError."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac([], tmp_path)


def test_dict_criterion_raises_value_error(tmp_path):
    """Dict criterion must raise ValueError."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac({}, tmp_path)


def test_bool_criterion_raises_value_error(tmp_path):
    """Bool (subclass of int) criterion must raise ValueError."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(True, tmp_path)


def test_bytes_criterion_raises_value_error(tmp_path):
    """Bytes criterion must raise ValueError, not silently treat as str."""
    with pytest.raises(ValueError):
        verify_quoted_substring_ac(b"MUST mention 'X'", tmp_path)


def test_value_error_message_mentions_type(tmp_path):
    """ValueError message should describe the bad type to aid debugging."""
    with pytest.raises(ValueError, match="str"):
        verify_quoted_substring_ac(None, tmp_path)


def test_does_not_silently_return_on_invalid_input(tmp_path):
    """Non-str input must NOT return a value — exception must propagate."""
    raised = False
    try:
        verify_quoted_substring_ac(object(), tmp_path)
    except ValueError:
        raised = True
    assert raised, "Expected ValueError but function returned silently"
