"""Error-path tests for enforce_ac_discipline.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (error path AC).
"""

from __future__ import annotations

import pytest

from bob.verifier_extension_ac_enforcer import enforce_ac_discipline

_VERIFIER_TARGET = "src/bob/enhanced_verification.py"


def test_non_list_acs_raises_value_error():
    """Passing a non-list for acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        enforce_ac_discipline("not a list", _VERIFIER_TARGET)


def test_none_acs_raises_value_error():
    """Passing None for acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError):
        enforce_ac_discipline(None, _VERIFIER_TARGET)


def test_tuple_acs_raises_value_error():
    """Passing a tuple (not a list) raises ValueError."""
    with pytest.raises(ValueError):
        enforce_ac_discipline(("behavior: test",), _VERIFIER_TARGET)


def test_int_acs_raises_value_error():
    """Passing an integer raises ValueError."""
    with pytest.raises(ValueError):
        enforce_ac_discipline(42, _VERIFIER_TARGET)


def test_dict_acs_raises_value_error():
    """Passing a dict raises ValueError."""
    with pytest.raises(ValueError):
        enforce_ac_discipline({"key": "value"}, _VERIFIER_TARGET)


def test_valid_inputs_do_not_raise():
    """Valid list input with verifier-extension target does not raise."""
    result = enforce_ac_discipline(
        ["behavior: some behavior", "structural: some structural"],
        _VERIFIER_TARGET,
        feature_id="error-path-valid",
    )
    assert result is not None
    assert result.is_verifier_extension is True


def test_valid_empty_list_does_not_raise():
    """Valid empty list does not raise."""
    result = enforce_ac_discipline([], _VERIFIER_TARGET, feature_id="error-path-empty")
    assert result is not None


def test_error_message_includes_type_name():
    """ValueError message includes the actual type name passed."""
    with pytest.raises(ValueError, match="str"):
        enforce_ac_discipline("not a list", _VERIFIER_TARGET)
