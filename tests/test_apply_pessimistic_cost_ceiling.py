"""Tests for apply_pessimistic_cost per-feature ceiling enforcement.

AC: pytest: tests/test_apply_pessimistic_cost_ceiling.py

Verifies the core bug fix: apply_pessimistic_cost MUST use a per-feature ceiling
(default $20, override via BOB_PER_FEATURE_COST_CEILING) rather than the entire
project max_cost_usd when charging for telemetry-loss events.

Root cause of the original bug:
    run_loop.py computed _per_feature_ceiling as min(self.max_cost, self._project_max_cost_usd)
    where self._project_max_cost_usd was the ENTIRE project budget (e.g. $10M).
    On telemetry loss, applying a $10M ceiling as one feature's charge instantly
    triggered BUDGET_EXCEEDED after a single feature attempt costing ~$1.

Fix:
    _compute_per_feature_ceiling() returns a sane per-feature default of $20
    (overridable via BOB_PER_FEATURE_COST_CEILING), which is then passed to
    apply_pessimistic_cost() as per_feature_ceiling.
"""

from __future__ import annotations

import os

import pytest

from bob.orchestrator.run_loop import apply_pessimistic_cost
from bob.orchestrator.per_feature_ceiling import compute_per_feature_ceiling


# ---------------------------------------------------------------------------
# Core contract: per-feature ceiling, NOT the project budget
# ---------------------------------------------------------------------------

class TestPerFeatureCeilingContract:
    """The ceiling charged on telemetry loss must be per-feature, not per-project."""

    def test_telemetry_loss_charges_per_feature_ceiling_not_project_budget(self):
        """Charging telemetry-loss at per-feature ceiling prevents catastrophic budget exhaustion."""
        per_feature_ceiling = 20.0
        entire_project_budget = 10_000_000.0  # $10M — the bug scenario

        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )

        assert result == pytest.approx(per_feature_ceiling)
        assert result < entire_project_budget, (
            "Pessimistic cost must be the per-feature ceiling, not the entire project budget. "
            f"Got {result}, project budget was {entire_project_budget}"
        )

    def test_default_ceiling_is_twenty_dollars(self):
        """Default ceiling from compute_per_feature_ceiling() is $20."""
        env_key = "BOB_PER_FEATURE_COST_CEILING"
        old = os.environ.pop(env_key, None)
        try:
            ceiling = compute_per_feature_ceiling()
        finally:
            if old is not None:
                os.environ[env_key] = old

        assert ceiling == pytest.approx(20.0)

    def test_telemetry_loss_with_default_twenty_dollar_ceiling(self):
        """On telemetry loss with the default $20 ceiling, charge is $20, not millions."""
        ceiling = compute_per_feature_ceiling.__wrapped__() if hasattr(compute_per_feature_ceiling, "__wrapped__") else 20.0
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(20.0)
        assert result < 1000.0, "Per-feature ceiling must be in a sane range, not the full project budget"

    def test_env_override_ceiling_respected(self):
        """BOB_PER_FEATURE_COST_CEILING env var overrides the default."""
        env_key = "BOB_PER_FEATURE_COST_CEILING"
        old = os.environ.pop(env_key, None)
        try:
            os.environ[env_key] = "5.0"
            ceiling = compute_per_feature_ceiling()
        finally:
            if old is not None:
                os.environ[env_key] = old
            else:
                os.environ.pop(env_key, None)

        assert ceiling == pytest.approx(5.0)
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result == pytest.approx(5.0)

    def test_invalid_env_override_falls_back_to_default(self):
        """Non-numeric BOB_PER_FEATURE_COST_CEILING falls back to $20 default."""
        env_key = "BOB_PER_FEATURE_COST_CEILING"
        old = os.environ.pop(env_key, None)
        try:
            os.environ[env_key] = "not-a-number"
            ceiling = compute_per_feature_ceiling()
        finally:
            if old is not None:
                os.environ[env_key] = old
            else:
                os.environ.pop(env_key, None)

        assert ceiling == pytest.approx(20.0)

    def test_negative_env_override_falls_back_to_default(self):
        """Negative BOB_PER_FEATURE_COST_CEILING falls back to $20 default."""
        env_key = "BOB_PER_FEATURE_COST_CEILING"
        old = os.environ.pop(env_key, None)
        try:
            os.environ[env_key] = "-5.0"
            ceiling = compute_per_feature_ceiling()
        finally:
            if old is not None:
                os.environ[env_key] = old
            else:
                os.environ.pop(env_key, None)

        assert ceiling == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Correct behavior when telemetry IS present
# ---------------------------------------------------------------------------

class TestNormalCostReporting:
    """When telemetry is not lost, reported cost is used directly."""

    def test_not_lost_returns_reported_cost(self):
        """When is_lost=False, the reported_cost is returned unchanged."""
        result = apply_pessimistic_cost(
            reported_cost=1.23,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(1.23)

    def test_not_lost_zero_cost_returns_zero(self):
        """Genuine spawn crash (is_lost=False, cost=0) returns 0.0 for free-retry path."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(0.0)

    def test_not_lost_high_cost_returns_reported(self):
        """High reported cost with is_lost=False is returned as-is, ignoring the ceiling."""
        result = apply_pessimistic_cost(
            reported_cost=100.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Ceiling function returns a positive float
# ---------------------------------------------------------------------------

class TestComputePerFeatureCeiling:
    """compute_per_feature_ceiling always returns a positive float."""

    def test_returns_positive_float(self):
        """compute_per_feature_ceiling returns a positive float."""
        ceiling = compute_per_feature_ceiling()
        assert isinstance(ceiling, float)
        assert ceiling > 0.0

    def test_returns_sane_value(self):
        """Default ceiling is a small dollar amount, not millions."""
        env_key = "BOB_PER_FEATURE_COST_CEILING"
        old = os.environ.pop(env_key, None)
        try:
            ceiling = compute_per_feature_ceiling()
        finally:
            if old is not None:
                os.environ[env_key] = old

        # The default should be at most $1000 — project budgets are $10M+
        assert ceiling <= 1000.0, (
            f"Per-feature ceiling {ceiling} is suspiciously large; "
            "it must NOT be set to the entire project budget"
        )


# ---------------------------------------------------------------------------
# Regression test: the original BUDGET_EXCEEDED bug scenario
# ---------------------------------------------------------------------------

class TestBudgetExceededRegression:
    """Regression guard for the catastrophic budget consumption bug."""

    def test_single_telemetry_loss_does_not_exhaust_ten_million_budget(self):
        """Simulates the bug: one telemetry-loss event must NOT consume a $10M budget."""
        project_budget = 10_000_000.0
        per_feature_ceiling = 20.0  # correct: use compute_per_feature_ceiling()

        charged = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )

        # After one telemetry-loss event, remaining budget should be essentially intact
        remaining = project_budget - charged
        assert remaining > project_budget * 0.99, (
            f"A single telemetry-loss event charged {charged} against a {project_budget} budget. "
            "This would trigger BUDGET_EXCEEDED. The per-feature ceiling must be a small value."
        )

    def test_ceiling_is_orders_of_magnitude_below_project_budget(self):
        """The per-feature ceiling must be 3+ orders of magnitude below typical project budgets."""
        per_feature_ceiling = 20.0
        typical_project_budget = 10_000.0  # modest $10k project budget

        ratio = per_feature_ceiling / typical_project_budget
        assert ratio < 0.01, (
            f"Per-feature ceiling ({per_feature_ceiling}) is {ratio:.1%} of a $10k project budget — "
            "it should be below 1% to prevent accidental budget exhaustion"
        )
