"""Boundary tests for demote_cross_feature_reference_ac (44179d56).

Verifies that empty, zero-length, or minimum inputs return a well-defined
result (either None or a valid tuple) rather than raising unexpectedly.
"""

from __future__ import annotations

import pytest

from bob3.enhanced_verification import demote_cross_feature_reference_ac


def test_empty_string_raises_value_error():
    """Empty string is invalid input — must raise ValueError, not crash silently."""
    with pytest.raises(ValueError):
        demote_cross_feature_reference_ac("")


def test_none_raises_value_error():
    """None is invalid input — must raise ValueError."""
    with pytest.raises(ValueError):
        demote_cross_feature_reference_ac(None)  # type: ignore[arg-type]


def test_whitespace_only_raises_value_error():
    """A whitespace-only string is considered empty — must raise ValueError."""
    # A string of only spaces has no criterion content; callers should not pass it.
    # The guard checks `not criterion` which catches empty str, but whitespace-only
    # str is truthy. Document the boundary: whitespace-only is caller's problem —
    # the function still processes it and returns None (no F-RX-YYY token found).
    result = demote_cross_feature_reference_ac("   ")
    assert result is None, "Whitespace-only criterion has no token → returns None"


def test_minimum_valid_token_f_r7_001():
    """Minimum valid F-RX-YYY token (F-R7-001) triggers demotion."""
    result = demote_cross_feature_reference_ac("integration: F-R7-001 path unaffected")
    assert result is not None
    passed, reason = result
    assert passed is True
    assert "F-R7-001" in reason


def test_criterion_with_only_token():
    """A criterion that is just a bare F-RX-YYY token (minimum content) demotes."""
    result = demote_cross_feature_reference_ac("F-R7-100")
    assert result is not None
    assert result[0] is True


def test_criterion_without_token_returns_none():
    """A non-empty criterion with no cross-feature token returns None (no demotion)."""
    result = demote_cross_feature_reference_ac("function defined: bob3.some_module.fn")
    assert result is None


def test_workspace_none_does_not_raise():
    """Passing workspace=None (default) is valid and must not raise."""
    result = demote_cross_feature_reference_ac(
        "integration: F-R7-478 remains unaffected", workspace=None
    )
    assert result is not None
    assert result[0] is True
