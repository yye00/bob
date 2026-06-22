"""Boundary tests for apply_pessimistic_cost per-feature ceiling behavior.

AC: pytest: tests/test_apply_pessimistic_cost_must_use_a_per_feature_ceil_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising (boundary case)

Verifies boundary conditions:
- Zero ceiling with is_lost=True → 0.0 (not an error)
- Very small ceiling (epsilon) → returns that exact small value
- Very large ceiling → returns that large value
- Minimum non-negative reported_cost → returned as-is when not lost
- None reported_cost → coerced to 0.0
- Negative reported_cost with is_lost=False → clamped to 0.0
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.run_loop import apply_pessimistic_cost


# --- Zero ceiling boundary ---

def test_zero_ceiling_is_lost_returns_zero_not_error():
    """Zero per_feature_ceiling with is_lost=True returns 0.0 (well-defined)."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=0.0,
    )
    assert result == pytest.approx(0.0)
    assert isinstance(result, float)


def test_zero_ceiling_not_lost_zero_cost_returns_zero():
    """Zero ceiling with is_lost=False and zero cost → 0.0 (free-retry case)."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=False,
        per_feature_ceiling=0.0,
    )
    assert result == pytest.approx(0.0)


# --- Minimum positive ceiling ---

def test_minimum_positive_ceiling_is_lost():
    """Minimum positive ceiling (1e-9) with is_lost=True returns that value."""
    tiny = 1e-9
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=tiny,
    )
    assert result == pytest.approx(tiny)


def test_unit_ceiling_is_lost():
    """Ceiling of exactly 1.0 with is_lost=True returns 1.0."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=1.0,
    )
    assert result == pytest.approx(1.0)


# --- Very large ceiling ---

def test_large_ceiling_is_lost_does_not_raise():
    """Very large ceiling (e.g. 1e8) with is_lost=True returns that value without error."""
    large = 1e8
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=large,
    )
    assert result == pytest.approx(large)


# --- None and negative reported_cost ---

def test_none_reported_cost_is_lost_false_returns_zero():
    """None reported_cost with is_lost=False coerces to 0.0 (well-defined, no raise)."""
    result = apply_pessimistic_cost(
        reported_cost=None,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(0.0)


def test_none_reported_cost_is_lost_true_returns_ceiling():
    """None reported_cost with is_lost=True returns per_feature_ceiling."""
    ceiling = 20.0
    result = apply_pessimistic_cost(
        reported_cost=None,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )
    assert result == pytest.approx(ceiling)


def test_negative_reported_cost_not_lost_clamps_to_zero():
    """Negative reported_cost with is_lost=False is clamped to 0.0."""
    result = apply_pessimistic_cost(
        reported_cost=-5.0,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(0.0)


def test_minimum_positive_reported_cost_not_lost():
    """Minimum positive reported_cost with is_lost=False returns that cost."""
    tiny = 1e-9
    result = apply_pessimistic_cost(
        reported_cost=tiny,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(tiny)


# --- Return type is always float ---

def test_return_type_is_float_is_lost_true():
    """apply_pessimistic_cost always returns float when is_lost=True."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=20.0,
    )
    assert isinstance(result, float)


def test_return_type_is_float_is_lost_false():
    """apply_pessimistic_cost always returns float when is_lost=False."""
    result = apply_pessimistic_cost(
        reported_cost=5.0,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert isinstance(result, float)


def test_return_type_is_float_zero_inputs():
    """apply_pessimistic_cost returns float even for all-zero inputs."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=False,
        per_feature_ceiling=0.0,
    )
    assert isinstance(result, float)
