"""Error-path tests for bob.baseline_gate.validate_collection.

AC: pytest: tests/test_stable_baseline_gate_error.py —
    invalid input raises ValueError and the function does not silently
    succeed (error path).
"""

from __future__ import annotations

import pytest

from bob_legacy.baseline_gate import validate_collection


# ---------------------------------------------------------------------------
# Invalid workspace type
# ---------------------------------------------------------------------------

def test_invalid_workspace_type_raises_value_error():
    """workspace that is not str, Path, or None raises ValueError."""
    with pytest.raises(ValueError, match="workspace"):
        validate_collection(42)


def test_workspace_as_list_raises_value_error():
    """workspace as list raises ValueError."""
    with pytest.raises(ValueError):
        validate_collection(["/some/path"])


def test_workspace_as_dict_raises_value_error():
    """workspace as dict raises ValueError."""
    with pytest.raises(ValueError):
        validate_collection({"path": "/some/path"})


def test_workspace_as_int_does_not_silently_succeed():
    """An invalid workspace type must not return a result — it must raise."""
    raised = False
    try:
        validate_collection(123)
    except ValueError:
        raised = True
    assert raised, "Expected ValueError for invalid workspace type"


# ---------------------------------------------------------------------------
# Invalid timeout type / value
# ---------------------------------------------------------------------------

def test_zero_timeout_raises_value_error():
    """timeout=0 is not positive; must raise ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        validate_collection(None, timeout=0)


def test_negative_timeout_raises_value_error():
    """Negative timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        validate_collection(None, timeout=-1)


def test_float_timeout_raises_value_error():
    """float timeout raises ValueError (must be int)."""
    with pytest.raises(ValueError, match="timeout"):
        validate_collection(None, timeout=30.0)


def test_none_timeout_raises_value_error():
    """None timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        validate_collection(None, timeout=None)


def test_bool_timeout_raises_value_error():
    """bool timeout (True/False) raises ValueError — bool is subclass of int but invalid."""
    with pytest.raises(ValueError, match="timeout"):
        validate_collection(None, timeout=True)


def test_string_timeout_raises_value_error():
    """String timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        validate_collection(None, timeout="120")


# ---------------------------------------------------------------------------
# Errors are not silent — validate_collection does not swallow them
# ---------------------------------------------------------------------------

def test_invalid_workspace_type_error_not_silently_swallowed():
    """Confirm the ValueError propagates and is not caught internally."""
    result = None
    exc = None
    try:
        result = validate_collection(object())
    except ValueError as e:
        exc = e
    assert exc is not None, "ValueError should have been raised"
    assert result is None, "No result should be returned on error"


def test_invalid_timeout_error_not_silently_swallowed():
    """Confirm timeout ValueError propagates and is not caught internally."""
    result = None
    exc = None
    try:
        result = validate_collection(None, timeout=-100)
    except ValueError as e:
        exc = e
    assert exc is not None, "ValueError should have been raised"
    assert result is None, "No result should be returned on error"
