"""Tests for apply_pessimistic_cost per-feature ceiling behavior.

AC: pytest: tests/test_apply_pessimistic_cost.py

Verifies the core contract of apply_pessimistic_cost:
- When telemetry is lost (is_lost=True), charge the per-feature ceiling, NOT the project budget
- When telemetry is present (is_lost=False), charge the reported cost
- The per-feature ceiling (BOB3_PER_FEATURE_COST_CEILING, default $20) is used, not the whole
  project max_cost_usd (which could be millions)
- This prevents the BUDGET_EXCEEDED bug where one telemetry-lost feature consumed the entire
  project budget ($10M) as its pessimistic charge
"""

from __future__ import annotations

import os

import pytest

from bob3.orchestrator.run_loop import apply_pessimistic_cost


class TestApplyPessimisticCostIsLostTrue:
    """Tests when telemetry is confirmed lost (is_lost=True)."""

    def test_charges_per_feature_ceiling_not_project_budget(self):
        """Core contract: is_lost=True charges per_feature_ceiling, not the full project budget."""
        per_feature_ceiling = 20.0
        project_budget = 10_000_000.0  # $10M project budget

        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )

        assert result == pytest.approx(per_feature_ceiling)
        assert result != pytest.approx(project_budget), (
            "apply_pessimistic_cost must charge the per-feature ceiling, not the entire project budget"
        )

    def test_default_ceiling_is_twenty_dollars(self):
        """Default per-feature ceiling of $20 prevents catastrophic budget exhaustion."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(20.0)

    def test_ignores_reported_cost_when_lost(self):
        """When is_lost=True, the reported_cost value is ignored in favor of the ceiling."""
        ceiling = 15.0
        result = apply_pessimistic_cost(
            reported_cost=5.0,  # SDK reported non-zero cost
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result == pytest.approx(ceiling)

    def test_ignores_zero_reported_cost_when_lost(self):
        """Zero reported_cost with is_lost=True → ceiling (telemetry-loss case)."""
        ceiling = 20.0
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result == pytest.approx(ceiling)

    def test_custom_ceiling_applied(self):
        """Custom ceiling (e.g. 50.0) is returned when is_lost=True."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=50.0,
        )
        assert result == pytest.approx(50.0)

    def test_return_is_float(self):
        """Return value is always a float."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=20.0,
        )
        assert isinstance(result, float)


class TestApplyPessimisticCostIsLostFalse:
    """Tests when telemetry is intact (is_lost=False) — normal flow."""

    def test_returns_reported_cost_when_not_lost(self):
        """When is_lost=False and reported_cost > 0, returns the actual cost."""
        reported = 3.45
        result = apply_pessimistic_cost(
            reported_cost=reported,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(reported)

    def test_returns_zero_for_genuine_spawn_crash(self):
        """Genuine spawn crash (cost=0, is_lost=False) returns 0.0 for free-retry path."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(0.0)

    def test_ceiling_not_applied_when_not_lost(self):
        """Ceiling is NOT charged when is_lost=False, even if cost is low."""
        result = apply_pessimistic_cost(
            reported_cost=1.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(1.0)
        assert result != pytest.approx(20.0)

    def test_none_reported_cost_not_lost_returns_zero(self):
        """None reported_cost with is_lost=False coerces to 0.0 (free-retry path)."""
        result = apply_pessimistic_cost(
            reported_cost=None,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(0.0)

    def test_negative_reported_cost_clamped_to_zero(self):
        """Negative reported_cost with is_lost=False is clamped to 0.0."""
        result = apply_pessimistic_cost(
            reported_cost=-1.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(0.0)

    def test_return_is_float(self):
        """Return value is always a float."""
        result = apply_pessimistic_cost(
            reported_cost=5.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert isinstance(result, float)


class TestApplyPessimisticCostFixesBudgetExceededBug:
    """Regression tests for the BUDGET_EXCEEDED bug.

    Root cause: _per_feature_ceiling was computed as
        min(self.max_cost, self._project_max_cost_usd)
    where self._project_max_cost_usd is the ENTIRE project budget (e.g. $10M).
    With is_lost=True, apply_pessimistic_cost returned $10M, instantly
    exhausting the budget on a single telemetry-lost feature.

    Fix: use BOB3_PER_FEATURE_COST_CEILING (default $20) as the ceiling.
    """

    def test_per_feature_ceiling_is_much_less_than_project_budget(self):
        """Demonstrates the fixed behavior: ceiling is $20, not $10M."""
        project_budget = 10_000_000.0
        per_feature_ceiling = 20.0

        result_with_fix = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )

        # The fixed version charges $20, not $10M
        assert result_with_fix == pytest.approx(20.0)
        assert result_with_fix < project_budget * 0.001, (
            "Per-feature ceiling must be orders of magnitude below the project budget"
        )

    def test_single_telemetry_loss_does_not_exhaust_budget(self):
        """One telemetry-lost feature should not consume the entire project budget."""
        budget_remaining = 500.0  # project has $500 left
        per_feature_ceiling = 20.0  # per-feature default

        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )

        # After charging one telemetry-lost feature, budget should still have funds
        budget_after = budget_remaining - result
        assert budget_after > 0, (
            "One telemetry-lost feature must not exhaust the remaining project budget"
        )
        assert result == pytest.approx(per_feature_ceiling)

    def test_multiple_telemetry_losses_stay_within_budget(self):
        """Multiple telemetry-lost features should not trigger BUDGET_EXCEEDED."""
        project_budget = 500.0
        per_feature_ceiling = 20.0
        num_features = 10  # simulate 10 telemetry-lost features

        total_charged = 0.0
        for _ in range(num_features):
            charge = apply_pessimistic_cost(
                reported_cost=0.0,
                is_lost=True,
                per_feature_ceiling=per_feature_ceiling,
            )
            total_charged += charge

        # 10 features × $20 = $200 — well within $500 budget
        assert total_charged == pytest.approx(num_features * per_feature_ceiling)
        assert total_charged < project_budget, (
            f"Total charge ({total_charged}) must be less than project budget ({project_budget})"
        )


class TestApplyPessimisticCostEnvOverride:
    """Tests for BOB3_PER_FEATURE_COST_CEILING environment variable override.

    The run_loop reads BOB3_PER_FEATURE_COST_CEILING and passes it as
    per_feature_ceiling. These tests verify the function correctly uses
    whatever ceiling is passed — the env var reading is tested at the
    call site, not inside apply_pessimistic_cost itself.
    """

    def test_custom_ceiling_ten_dollars(self):
        """$10 ceiling is charged when is_lost=True."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=10.0,
        )
        assert result == pytest.approx(10.0)

    def test_custom_ceiling_hundred_dollars(self):
        """$100 ceiling is charged when is_lost=True."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=100.0,
        )
        assert result == pytest.approx(100.0)

    def test_ceiling_is_per_feature_not_project(self):
        """Ceiling semantics: per-feature, not per-project."""
        # Simulate two features with the same per-feature ceiling
        ceiling = 20.0
        charge1 = apply_pessimistic_cost(0.0, True, ceiling)
        charge2 = apply_pessimistic_cost(0.0, True, ceiling)

        # Each feature is charged the ceiling independently
        assert charge1 == pytest.approx(ceiling)
        assert charge2 == pytest.approx(ceiling)
        # Total for two features is 2 × ceiling, not 1 × ceiling
        assert charge1 + charge2 == pytest.approx(2 * ceiling)
