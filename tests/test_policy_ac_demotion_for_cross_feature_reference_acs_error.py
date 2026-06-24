"""Error-path tests for demote_cross_feature_reference_ac (44179d56).

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (i.e. never returns a passing result for bad inputs).
"""

from __future__ import annotations

import pytest

from bob.enhanced_verification import demote_cross_feature_reference_ac


def test_none_input_raises():
    """None raises ValueError — not silently demoted or returning None."""
    with pytest.raises(ValueError, match="must be a non-empty str"):
        demote_cross_feature_reference_ac(None)  # type: ignore[arg-type]


def test_empty_string_raises():
    """Empty string raises ValueError."""
    with pytest.raises(ValueError, match="must be a non-empty str"):
        demote_cross_feature_reference_ac("")


def test_integer_input_raises():
    """An integer instead of a string raises ValueError."""
    with pytest.raises(ValueError):
        demote_cross_feature_reference_ac(42)  # type: ignore[arg-type]


def test_list_input_raises():
    """A list raises ValueError."""
    with pytest.raises(ValueError):
        demote_cross_feature_reference_ac(["F-R7-100"])  # type: ignore[arg-type]


def test_error_not_silently_passing():
    """Invalid input must not silently return a passing result (True, ...) tuple."""
    for bad in (None, "", 0, [], {}):
        try:
            result = demote_cross_feature_reference_ac(bad)  # type: ignore[arg-type]
            # If no exception, result must not be a passing (True, ...) tuple.
            assert result is None or result[0] is not True, (
                f"Invalid input {bad!r} must not silently pass as a demoted PASS"
            )
        except (ValueError, TypeError):
            pass  # Expected — invalid input correctly rejected
