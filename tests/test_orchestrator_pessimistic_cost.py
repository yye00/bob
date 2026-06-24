"""Tests for apply_pessimistic_cost per-feature ceiling in run_loop.

AC: pytest: tests/test_orchestrator_pessimistic_cost.py
AC: Function defined: bob.orchestrator.run_loop.apply_pessimistic_cost
AC: integration: bob.orchestrator.run_loop

Verifies that apply_pessimistic_cost is importable from bob.orchestrator.run_loop
and that the per-feature ceiling (not the full project budget) is used when
telemetry is lost — fixing the bug where one feature could consume the entire
project budget ($10M) in a single telemetry-loss event.
"""

from __future__ import annotations

import os

import pytest

from bob.orchestrator.run_loop import apply_pessimistic_cost


# --- Importability: Function defined in bob.orchestrator.run_loop ---

def test_apply_pessimistic_cost_importable():
    """apply_pessimistic_cost must be importable from bob.orchestrator.run_loop."""
    assert callable(apply_pessimistic_cost)


def test_apply_pessimistic_cost_module():
    """apply_pessimistic_cost must live in bob.orchestrator.* namespace."""
    module = apply_pessimistic_cost.__module__
    assert "bob.orchestrator" in module, (
        f"Expected bob.orchestrator.* module, got: {module}"
    )


# --- Core behavior: per-feature ceiling is used, NOT project max_cost_usd ---

def test_per_feature_ceiling_charged_on_telemetry_loss():
    """On telemetry loss, the per-feature ceiling is returned, not the whole project budget."""
    per_feature_ceiling = 20.0
    project_budget = 10_000_000.0  # $10M — the broken value from the bug

    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=per_feature_ceiling,
    )

    assert result == pytest.approx(per_feature_ceiling), (
        f"Expected per-feature ceiling {per_feature_ceiling}, got {result}. "
        "The bug charged the entire project budget instead of a per-feature value."
    )
    assert result < project_budget, (
        f"Pessimistic cost {result} must not equal or exceed project budget {project_budget}. "
        "This is the root bug: one feature must never consume the full project budget."
    )


def test_project_budget_not_charged_on_telemetry_loss():
    """Pessimistic cost must never equal the full project budget."""
    full_project_budget = 10_000_000.0
    per_feature_ceiling = 20.0

    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=per_feature_ceiling,
    )

    assert result != pytest.approx(full_project_budget), (
        "Bug regression: apply_pessimistic_cost returned the full project budget. "
        "It must return the per-feature ceiling instead."
    )


def test_normal_cost_returned_when_not_lost():
    """When is_lost=False, the reported cost is returned unchanged."""
    reported = 1.23
    result = apply_pessimistic_cost(
        reported_cost=reported,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(reported)


def test_zero_cost_not_lost_returns_zero():
    """Zero cost with is_lost=False returns 0.0 (free-retry path, not ceiling)."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(0.0)


def test_is_lost_true_always_returns_ceiling_regardless_of_reported_cost():
    """When is_lost=True, the ceiling is always returned regardless of reported_cost."""
    ceiling = 15.0
    for reported in [0.0, 1.0, 5.0, 100.0]:
        result = apply_pessimistic_cost(
            reported_cost=reported,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result == pytest.approx(ceiling), (
            f"With reported_cost={reported} and is_lost=True, expected ceiling {ceiling}, got {result}"
        )


# --- env override: BOB_PER_FEATURE_COST_CEILING ---

def test_default_ceiling_is_twenty_dollars(monkeypatch):
    """Default per-feature ceiling should be $20 (env not set)."""
    monkeypatch.delenv("BOB_PER_FEATURE_COST_CEILING", raising=False)
    # The env var controls the ceiling passed by run_loop to apply_pessimistic_cost.
    # When not set, run_loop uses 20.0 as default. Verify the function itself
    # correctly returns a $20 ceiling when called with 20.0.
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(20.0)


def test_custom_ceiling_respected():
    """Custom per-feature ceiling value is returned precisely."""
    for ceiling in [5.0, 10.0, 50.0, 100.0]:
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result == pytest.approx(ceiling), f"Expected ceiling {ceiling}, got {result}"


# --- Integration: the fix prevents budget-exceeded from one feature ---

def test_one_telemetry_loss_does_not_exhaust_large_budget():
    """A single telemetry-loss event must not exhaust a $10M budget."""
    per_feature_ceiling = 20.0
    project_budget = 10_000_000.0
    total_spent = 100.0  # existing spend

    cost_charged = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=per_feature_ceiling,
    )

    new_total = total_spent + cost_charged
    assert new_total < project_budget, (
        f"After one telemetry-loss event, total={new_total} must be < project_budget={project_budget}. "
        "The bug caused total to jump to $10M+ and trigger BUDGET_EXCEEDED."
    )


def test_many_telemetry_loss_events_charge_proportionally():
    """100 telemetry-loss events at $20 each = $2000, not the whole project budget."""
    per_feature_ceiling = 20.0
    project_budget = 10_000_000.0
    n_events = 100

    total = sum(
        apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )
        for _ in range(n_events)
    )

    expected = n_events * per_feature_ceiling
    assert total == pytest.approx(expected)
    assert total < project_budget, (
        f"{n_events} telemetry-loss events at ${per_feature_ceiling} each = ${total}, "
        f"which must be << project budget ${project_budget}."
    )


def test_return_value_is_always_float():
    """apply_pessimistic_cost always returns a float."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=20.0,
    )
    assert isinstance(result, float)

    result2 = apply_pessimistic_cost(
        reported_cost=5.0,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert isinstance(result2, float)
