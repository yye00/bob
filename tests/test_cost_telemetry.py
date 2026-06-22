"""Tests for bob3.cost_telemetry — zero-cost MUST NOT disable budget enforcement.

AC: pytest: tests/test_cost_telemetry.py

Covers:
- validate_cost_nonzero: telemetry-loss detection and ceiling application
- apply_ceiling_on_telemetry_loss: direct ceiling application primitive
- enforce_budget_on_zero_cost_with_work_events: unified entry point
- EnforceBudgetWithWorkEventsResult: result object structure
"""

from __future__ import annotations

import pytest

from bob3.cost_telemetry import (
    EnforceBudgetWithWorkEventsResult,
    apply_ceiling_on_telemetry_loss,
    enforce_budget_on_zero_cost_with_work_events,
    validate_cost_nonzero,
)


class TestEnforceBudgetWithWorkEventsResult:
    """EnforceBudgetWithWorkEventsResult stores cost_to_charge and telemetry_lost."""

    def test_stores_cost_to_charge(self):
        r = EnforceBudgetWithWorkEventsResult(cost_to_charge=5.0, telemetry_lost=True)
        assert r.cost_to_charge == pytest.approx(5.0)

    def test_stores_telemetry_lost(self):
        r = EnforceBudgetWithWorkEventsResult(cost_to_charge=0.0, telemetry_lost=False)
        assert r.telemetry_lost is False

    def test_cost_to_charge_coerced_to_float(self):
        r = EnforceBudgetWithWorkEventsResult(cost_to_charge=3, telemetry_lost=False)
        assert isinstance(r.cost_to_charge, float)

    def test_telemetry_lost_coerced_to_bool(self):
        r = EnforceBudgetWithWorkEventsResult(cost_to_charge=0.0, telemetry_lost=1)
        assert isinstance(r.telemetry_lost, bool)
        assert r.telemetry_lost is True


class TestValidateCostNonzero:
    """validate_cost_nonzero: enforce budget when telemetry may be lost."""

    def test_zero_cost_high_work_events_detects_telemetry_loss(self):
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id="test-feature-001",
        )
        assert isinstance(result, EnforceBudgetWithWorkEventsResult)
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_zero_cost_zero_work_events_is_free_retry(self):
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="test-feature-002",
        )
        assert isinstance(result, EnforceBudgetWithWorkEventsResult)
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_none_cost_high_work_events_detects_telemetry_loss(self):
        result = validate_cost_nonzero(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=8.0,
            feature_id="test-feature-003",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(8.0)

    def test_positive_cost_returned_as_is(self):
        result = validate_cost_nonzero(
            reported_cost=2.5,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="test-feature-004",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(2.5)

    def test_zero_cost_exactly_at_threshold_not_lost(self):
        """Default threshold is 100; at exactly 100 events, not lost."""
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="test-feature-at-threshold",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_zero_cost_one_above_threshold_is_lost(self):
        """At 101 events (> 100 threshold), telemetry is considered lost."""
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="test-feature-above-threshold",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_returns_correct_result_type(self):
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=5.0,
            feature_id="test-feature-type",
        )
        assert isinstance(result, EnforceBudgetWithWorkEventsResult)
        assert isinstance(result.cost_to_charge, float)
        assert isinstance(result.telemetry_lost, bool)

    def test_accepts_exit_code_and_attempt_number(self):
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=5.0,
            feature_id="test-feature-extra-params",
            exit_code=1,
            attempt_number=3,
        )
        assert isinstance(result, EnforceBudgetWithWorkEventsResult)
        assert result.telemetry_lost is True


class TestApplyCeilingOnTelemetryLoss:
    """apply_ceiling_on_telemetry_loss: return ceiling when telemetry is lost."""

    def test_zero_cost_high_work_returns_ceiling(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=10.0,
        )
        assert result == pytest.approx(10.0)

    def test_zero_cost_zero_work_returns_zero(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
        )
        assert result == pytest.approx(0.0)

    def test_none_cost_high_work_returns_ceiling(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=None,
            work_events=200,
            per_feature_ceiling=7.5,
        )
        assert result == pytest.approx(7.5)

    def test_positive_cost_returned_unchanged(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=3.14,
            work_events=1000,
            per_feature_ceiling=10.0,
        )
        assert result == pytest.approx(3.14)

    def test_returns_float(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=10.0,
        )
        assert isinstance(result, float)

    def test_zero_cost_at_threshold_returns_zero(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
        )
        assert result == pytest.approx(0.0)

    def test_zero_cost_above_threshold_returns_ceiling(self):
        result = apply_ceiling_on_telemetry_loss(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
        )
        assert result == pytest.approx(10.0)


class TestEnforceBudgetOnZeroCostWithWorkEvents:
    """enforce_budget_on_zero_cost_with_work_events: unified entry point."""

    def test_zero_cost_high_work_applies_ceiling(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id="test-unified-001",
            exit_code=1,
            attempt_number=1,
        )
        assert isinstance(result, EnforceBudgetWithWorkEventsResult)
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_zero_cost_zero_work_free_retry(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="test-unified-002",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_positive_cost_pass_through(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=1.23,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id="test-unified-003",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(1.23)

    def test_result_type(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=5.0,
            feature_id="test-unified-type",
        )
        assert isinstance(result, EnforceBudgetWithWorkEventsResult)
        assert isinstance(result.cost_to_charge, float)
        assert isinstance(result.telemetry_lost, bool)


class TestCoreInvariant:
    """Core invariant: zero-reported-cost MUST NOT disable budget enforcement."""

    def test_zero_cost_with_substantial_work_charges_ceiling_not_zero(self):
        """The key invariant: cost==0 + work > threshold → ceiling charged, not 0."""
        result = validate_cost_nonzero(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id="invariant-test",
        )
        assert result.cost_to_charge > 0.0, (
            "Budget enforcement MUST NOT be disabled when zero cost and high work events"
        )
        assert result.telemetry_lost is True

    def test_zero_cost_budget_enforcement_never_disabled_for_work(self):
        """Budget enforcement remains active when any work was observed."""
        for work_events in [101, 500, 1000, 50000, 176217]:
            result = apply_ceiling_on_telemetry_loss(
                reported_cost=0.0,
                work_events=work_events,
                per_feature_ceiling=10.0,
            )
            assert result == pytest.approx(10.0), (
                f"Expected ceiling for work_events={work_events}, got {result}"
            )
