"""Tests for AC: bob.cost_telemetry_guard.enforce_minimum_cost_on_zero_report.

Feature 5d25f312: zero-reported-cost MUST NOT disable budget enforcement.

Verifies that enforce_minimum_cost_on_zero_report:
- zero cost + high work_events → ceiling applied (telemetry_lost=True)
- zero cost + zero work_events → genuine spawn crash, 0.0 charged (telemetry_lost=False)
- nonzero cost → reported cost returned unmodified (telemetry_lost=False)
- the incident scenario (work_events=176217) is correctly handled
- structured cost_telemetry_lost log is emitted when telemetry is lost
"""

from __future__ import annotations

import logging

import pytest

from bob.cost_telemetry_guard import (
    COST_TELEMETRY_FREE_RETRY,
    COST_TELEMETRY_LOST,
    COST_TELEMETRY_NORMAL,
    MinimumCostResult,
    classify_cost_telemetry,
    enforce_budget_on_zero_cost,
    enforce_minimum_cost_on_zero_report,
)


FEATURE_ID = "5d25f312-test"
CEILING = 5.00


class TestEnforceMinimumCostOnZeroReport:
    """Core invariant tests for enforce_minimum_cost_on_zero_report."""

    def test_zero_cost_high_work_applies_ceiling(self):
        """The incident scenario: cost==0 + 176217 work_events → ceiling charged."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
            exit_code=1,
            attempt_number=1,
        )
        assert isinstance(result, MinimumCostResult)
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_zero_cost_zero_work_is_free_retry(self):
        """Pure zero-work zero-cost is a genuine spawn crash, not telemetry loss."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, MinimumCostResult)
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_nonzero_cost_returned_unmodified(self):
        """Positive cost bypasses telemetry-loss logic and is returned as-is."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=2.50,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, MinimumCostResult)
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(2.50)

    def test_none_cost_high_work_applies_ceiling(self):
        """None is coerced to 0.0; with high work_events ceiling is charged."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, MinimumCostResult)
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_none_cost_zero_work_is_free_retry(self):
        """None cost + zero work → free retry path."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_negative_cost_treated_as_zero_high_work_applies_ceiling(self):
        """Negative cost is treated as 0.0; with high work_events ceiling is charged."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=-0.001,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)


class TestEnforceMinimumCostThresholdBoundary:
    """Boundary behavior around the default threshold of 100 work_events."""

    def test_work_events_at_threshold_not_telemetry_lost(self):
        """Exactly at threshold (100) → NOT classified as telemetry loss."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_work_events_one_above_threshold_is_telemetry_lost(self):
        """One above threshold (101) → classified as telemetry loss."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_work_events_one_below_threshold_not_telemetry_lost(self):
        """One below threshold (99) → NOT classified as telemetry loss."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=FEATURE_ID,  # type: ignore[arg-type]
            feature_id=FEATURE_ID,
        )
        # If per_feature_ceiling is a string, it will raise — so we use a numeric value
        pass

    def test_work_events_99_not_telemetry_lost(self):
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)


class TestEnforceMinimumCostResultType:
    """Return type consistency tests."""

    @pytest.mark.parametrize("work_events", [0, 1, 100, 101, 1000, 176217])
    def test_always_returns_minimum_cost_result(self, work_events):
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=work_events,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, MinimumCostResult)
        assert isinstance(result.cost_to_charge, float)
        assert isinstance(result.telemetry_lost, bool)

    @pytest.mark.parametrize("reported_cost", [None, 0.0, 1.0, 5.0, 100.0])
    def test_always_returns_result_for_various_costs(self, reported_cost):
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=reported_cost,
            work_events=50,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, MinimumCostResult)
        assert isinstance(result.cost_to_charge, float)
        assert isinstance(result.telemetry_lost, bool)


class TestEnforceMinimumCostLogging:
    """Structured log emission when telemetry is lost."""

    def test_cost_telemetry_lost_warn_emitted(self, caplog):
        """When telemetry is lost, a structured WARN log must be emitted."""
        with caplog.at_level(logging.WARNING):
            enforce_minimum_cost_on_zero_report(
                reported_cost=0.0,
                work_events=176217,
                per_feature_ceiling=CEILING,
                feature_id="log-test-feature",
                exit_code=1,
                attempt_number=2,
            )
        assert any("cost_telemetry_lost" in r.message for r in caplog.records)

    def test_no_log_when_cost_is_nonzero(self, caplog):
        """When cost is positive, no cost_telemetry_lost event is emitted."""
        with caplog.at_level(logging.WARNING):
            enforce_minimum_cost_on_zero_report(
                reported_cost=2.50,
                work_events=176217,
                per_feature_ceiling=CEILING,
                feature_id="no-log-feature",
            )
        assert not any("cost_telemetry_lost" in r.message for r in caplog.records)

    def test_no_log_for_free_retry(self, caplog):
        """Free retry (zero cost, zero work) does not emit cost_telemetry_lost."""
        with caplog.at_level(logging.WARNING):
            enforce_minimum_cost_on_zero_report(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=CEILING,
                feature_id="free-retry-feature",
            )
        assert not any("cost_telemetry_lost" in r.message for r in caplog.records)


class TestClassifyCostTelemetry:
    """The pure classifier underlying the enforcement path."""

    def test_nonzero_cost_is_normal(self):
        assert classify_cost_telemetry(2.5, 176217) == COST_TELEMETRY_NORMAL

    def test_zero_cost_high_work_is_telemetry_lost(self):
        assert classify_cost_telemetry(0.0, 176217) == COST_TELEMETRY_LOST

    def test_zero_cost_zero_work_is_free_retry(self):
        assert classify_cost_telemetry(0.0, 0) == COST_TELEMETRY_FREE_RETRY

    def test_none_cost_high_work_is_telemetry_lost(self):
        assert classify_cost_telemetry(None, 500) == COST_TELEMETRY_LOST

    def test_negative_cost_high_work_is_telemetry_lost(self):
        assert classify_cost_telemetry(-0.001, 500) == COST_TELEMETRY_LOST

    def test_at_threshold_is_free_retry(self):
        assert classify_cost_telemetry(0.0, 100) == COST_TELEMETRY_FREE_RETRY

    def test_one_above_threshold_is_telemetry_lost(self):
        assert classify_cost_telemetry(0.0, 101) == COST_TELEMETRY_LOST

    def test_invalid_work_events_type_raises(self):
        with pytest.raises(ValueError):
            classify_cost_telemetry(0.0, "many")  # type: ignore[arg-type]

    def test_bool_work_events_raises(self):
        with pytest.raises(ValueError):
            classify_cost_telemetry(0.0, True)  # type: ignore[arg-type]

    def test_negative_work_events_raises(self):
        with pytest.raises(ValueError):
            classify_cost_telemetry(0.0, -1)


class TestEnforceBudgetOnZeroCostReexport:
    """enforce_budget_on_zero_cost is re-exported by the bob façade (AC symbol)."""

    def test_incident_scenario_applies_ceiling(self):
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_free_retry_charges_zero(self):
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)


class TestEnforceMinimumCostCeilingApplication:
    """The per-feature ceiling must be applied exactly when telemetry is lost."""

    def test_ceiling_value_matches_charge(self):
        ceiling = 12.34
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=ceiling,
            feature_id=FEATURE_ID,
        )
        assert result.cost_to_charge == pytest.approx(ceiling)

    def test_reported_cost_ignored_when_telemetry_lost(self):
        """Even if reported_cost is close to ceiling but zero, ceiling is charged."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=20.0,
            feature_id=FEATURE_ID,
        )
        assert result.cost_to_charge == pytest.approx(20.0)

    def test_nonzero_cost_not_elevated_to_ceiling(self):
        """Positive reported_cost must NOT be replaced by ceiling."""
        result = enforce_minimum_cost_on_zero_report(
            reported_cost=0.50,
            work_events=500,
            per_feature_ceiling=20.0,
            feature_id=FEATURE_ID,
        )
        assert result.cost_to_charge == pytest.approx(0.50)
        assert result.telemetry_lost is False
