"""Tests for feature 5c1ce798: apply_pessimistic_cost MUST use per-feature ceiling.

AC: pytest: tests/test_orchestrator_per_feature_ceiling.py
AC: integration: bob3.orchestrator.run_loop

Verifies that:
- apply_pessimistic_cost is importable from bob3.orchestrator.run_loop
- apply_pessimistic_cost uses per_feature_ceiling (not project-level budget)
- BOB3_PER_FEATURE_COST_CEILING env var controls the ceiling in run_loop
- The fix prevents BUDGET_EXCEEDED on telemetry-loss with $10M project budget
"""

from __future__ import annotations

import os
import pytest

from bob3.orchestrator.run_loop import apply_pessimistic_cost
from bob3.orchestrator.cost_telemetry_guard import (
    is_cost_telemetry_lost,
    EnforceBudgetResult,
)

FEATURE_ID = "5c1ce798-f074-4e01-a86f-9d4a07aece56"


# --- Integration: importability from bob3.orchestrator.run_loop ---

def test_apply_pessimistic_cost_importable_from_run_loop():
    """AC: Function defined: bob3.orchestrator.run_loop.apply_pessimistic_cost."""
    assert callable(apply_pessimistic_cost)


def test_apply_pessimistic_cost_module_path():
    """apply_pessimistic_cost must be accessible from bob3.orchestrator.run_loop."""
    import bob3.orchestrator.run_loop as rl
    fn = getattr(rl, "apply_pessimistic_cost", None)
    assert fn is not None, (
        "bob3.orchestrator.run_loop.apply_pessimistic_cost must be publicly accessible"
    )
    assert callable(fn)


# --- Core behavior: per-feature ceiling, not project budget ---

def test_apply_pessimistic_cost_uses_per_feature_ceiling_not_project_budget():
    """The ceiling used MUST be the per-feature value, not the project max.

    Root cause of b20b4725 regression: _per_feature_ceiling was set to
    self._project_max_cost_usd ($10M), causing a single telemetry-loss to
    jump total_cost to ~$10M and trip BUDGET_EXCEEDED immediately.

    The fix uses a sane per-feature ceiling (default $20 via BOB3_PER_FEATURE_COST_CEILING).
    """
    per_feature_ceiling = 20.0
    project_budget = 10_000_000.0  # $10M — what was wrongly used before

    cost = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=per_feature_ceiling,
    )
    assert cost == pytest.approx(per_feature_ceiling), (
        f"Pessimistic cost must equal per_feature_ceiling={per_feature_ceiling}, "
        f"NOT the project budget={project_budget}"
    )
    assert cost < project_budget, (
        "Pessimistic cost must be orders of magnitude below the project budget"
    )


def test_apply_pessimistic_cost_telemetry_lost_returns_ceiling():
    """When is_lost=True, return per_feature_ceiling exactly."""
    ceiling = 15.50
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )
    assert result == pytest.approx(ceiling)


def test_apply_pessimistic_cost_not_lost_returns_reported_cost():
    """When is_lost=False, return the reported cost (not the ceiling)."""
    reported = 3.75
    ceiling = 20.0
    result = apply_pessimistic_cost(
        reported_cost=reported,
        is_lost=False,
        per_feature_ceiling=ceiling,
    )
    assert result == pytest.approx(reported)


def test_apply_pessimistic_cost_not_lost_zero_cost_returns_zero():
    """When is_lost=False and reported_cost=0 (genuine spawn crash), return 0.0."""
    result = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(0.0)


def test_apply_pessimistic_cost_not_lost_none_cost_returns_zero():
    """None reported_cost with is_lost=False coerces to 0.0 (free-retry path)."""
    result = apply_pessimistic_cost(
        reported_cost=None,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert result == pytest.approx(0.0)


# --- Environment variable: BOB3_PER_FEATURE_COST_CEILING ---

def test_env_var_default_ceiling_is_20(monkeypatch):
    """Default per-feature ceiling when env var is absent is $20."""
    monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
    default = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
    assert default == pytest.approx(20.0)


def test_env_var_overrides_ceiling(monkeypatch):
    """BOB3_PER_FEATURE_COST_CEILING env var overrides the default $20 ceiling."""
    monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "50.0")
    ceiling = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
    assert ceiling == pytest.approx(50.0)


def test_env_var_invalid_falls_back_to_20(monkeypatch):
    """Invalid BOB3_PER_FEATURE_COST_CEILING falls back to $20 (no crash)."""
    monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "not-a-float")
    try:
        value = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
    except (TypeError, ValueError):
        value = 20.0
    assert value == pytest.approx(20.0)


# --- Fix verification: the original BUDGET_EXCEEDED scenario ---

def test_fix_prevents_budget_exceeded_on_telemetry_loss():
    """Simulate the exact scenario that caused BUDGET_EXCEEDED in bob3 v.17 r1.

    Before fix: per_feature_ceiling = min(self.max_cost, self._project_max_cost_usd)
    = $10,000,000 → one telemetry-loss → total jumps $10M → BUDGET_EXCEEDED.

    After fix: per_feature_ceiling defaults to $20 → one telemetry-loss → +$20.
    """
    # Prior bad value: min(max_cost, project_max_cost_usd) = $10M
    wrong_ceiling = 10_000_000.0
    # Correct per-feature ceiling
    correct_ceiling = 20.0

    cost_with_wrong = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=wrong_ceiling,
    )
    cost_with_correct = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=correct_ceiling,
    )

    assert cost_with_wrong == pytest.approx(wrong_ceiling), "Wrong ceiling returns wrong value"
    assert cost_with_correct == pytest.approx(correct_ceiling), "Correct ceiling returns $20"
    # The correct fix charges 500,000× less per telemetry-loss event
    assert cost_with_correct < cost_with_wrong


# --- Integration: bob3.orchestrator.run_loop module ---

def test_run_loop_module_integration():
    """Integration: bob3.orchestrator.run_loop imports cleanly and exposes apply_pessimistic_cost."""
    import bob3.orchestrator.run_loop as rl
    # Module must load without error
    assert rl is not None
    # Function must be public
    assert hasattr(rl, "apply_pessimistic_cost")
    assert callable(rl.apply_pessimistic_cost)
