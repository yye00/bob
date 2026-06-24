"""Error-path tests for bob.orchestrator.detect_pending_successor_verify (feature 46265d9b).

Verifies that invalid input raises ValueError and the function does not
silently succeed (error path AC).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Error path: integer input raises ValueError
# ---------------------------------------------------------------------------


def test_integer_input_raises_value_error():
    """Integer acceptance_criteria must raise ValueError, not silently succeed."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError):
        detect_pending_successor_verify(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: dict input raises ValueError
# ---------------------------------------------------------------------------


def test_dict_input_raises_value_error():
    """Dict acceptance_criteria must raise ValueError, not return False."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError):
        detect_pending_successor_verify({"key": "value"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: set input raises ValueError
# ---------------------------------------------------------------------------


def test_set_input_raises_value_error():
    """Set acceptance_criteria must raise ValueError."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError):
        detect_pending_successor_verify({"behavior: enhanced_verification"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: bool input raises ValueError
# ---------------------------------------------------------------------------


def test_bool_input_raises_value_error():
    """Bool acceptance_criteria must raise ValueError (bool is not str or list)."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError):
        detect_pending_successor_verify(True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: float input raises ValueError
# ---------------------------------------------------------------------------


def test_float_input_raises_value_error():
    """Float acceptance_criteria must raise ValueError."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError):
        detect_pending_successor_verify(3.14)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: ValueError message describes the bad type
# ---------------------------------------------------------------------------


def test_value_error_message_mentions_type():
    """ValueError message must mention the invalid type received."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError, match="int"):
        detect_pending_successor_verify(99)  # type: ignore[arg-type]


def test_value_error_message_mentions_dict_type():
    """ValueError message must mention 'dict' when a dict is passed."""
    from bob.orchestrator import detect_pending_successor_verify
    with pytest.raises(ValueError, match="dict"):
        detect_pending_successor_verify({"a": "b"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: function does not silently succeed (no return value)
# ---------------------------------------------------------------------------


def test_does_not_return_on_integer_input():
    """Function must raise rather than returning any value for integer input."""
    from bob.orchestrator import detect_pending_successor_verify
    raised = False
    try:
        detect_pending_successor_verify(0)  # type: ignore[arg-type]
    except ValueError:
        raised = True
    assert raised, "ValueError must be raised for integer 0"


def test_does_not_return_on_list_of_ints():
    """A list of ints (not strings) must still work — each element is cast to str."""
    # Lists are a valid type; elements coerced to str by the underlying function.
    # This is NOT an error path — list is an accepted type even if items are ints.
    from bob.orchestrator import detect_pending_successor_verify
    # Should not raise; non-string list items are coerced to str.
    result = detect_pending_successor_verify([1, 2, 3])  # type: ignore[list-item]
    assert isinstance(result, bool)
