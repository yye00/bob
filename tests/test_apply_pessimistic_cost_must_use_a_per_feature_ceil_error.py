"""Error path tests for apply_pessimistic_cost per-feature ceiling behavior.

AC: pytest: tests/test_apply_pessimistic_cost_must_use_a_per_feature_ceil_error.py
    — invalid input raises ValueError and the function does not silently succeed (error path)

Verifies error paths:
- Invalid (non-numeric) per_feature_ceiling raises ValueError or TypeError
- Invalid (non-bool) is_lost where it causes a type mismatch
- Function does not silently succeed on clearly invalid ceiling types
"""

from __future__ import annotations

import pytest

from bob.orchestrator.run_loop import apply_pessimistic_cost


# --- Invalid per_feature_ceiling type ---

def test_string_ceiling_raises_on_is_lost_true():
    """Non-numeric per_feature_ceiling string raises ValueError (not silent success)."""
    with pytest.raises((ValueError, TypeError)):
        apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling="invalid",
        )


def test_none_ceiling_raises_on_is_lost_true():
    """None per_feature_ceiling raises TypeError (not silent success) when is_lost=True."""
    with pytest.raises((TypeError, AttributeError)):
        apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=None,
        )


def test_list_ceiling_raises():
    """List per_feature_ceiling is not a valid numeric type and must raise."""
    with pytest.raises((TypeError, ValueError)):
        apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=[20.0],
        )


def test_dict_ceiling_raises():
    """Dict per_feature_ceiling is not valid and must raise."""
    with pytest.raises((TypeError, ValueError)):
        apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling={"ceiling": 20},
        )


# --- Verify no silent success on invalid input ---

def test_invalid_ceiling_type_does_not_return_zero():
    """A string ceiling MUST NOT silently return 0.0 — it must raise."""
    raised = False
    try:
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling="not-a-number",
        )
    except (ValueError, TypeError):
        raised = True

    assert raised, (
        "apply_pessimistic_cost must raise on invalid per_feature_ceiling, "
        "not silently return a default or zero"
    )


def test_invalid_ceiling_type_does_not_silently_succeed():
    """None ceiling with is_lost=True must not silently return any value."""
    raised = False
    try:
        apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=None,
        )
    except (TypeError, AttributeError, ValueError):
        raised = True

    assert raised, (
        "apply_pessimistic_cost must not silently succeed when per_feature_ceiling is None"
    )
