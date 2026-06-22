"""Tests for bob3.cost_telemetry_guardian.enforce_cost_floor_on_zero_report.

AC: pytest: tests/test_cost_telemetry_guardian.py

Verifies the core invariant: zero-reported-cost MUST NOT disable budget
enforcement when substantial work was performed (work_events > threshold).
"""

from __future__ import annotations

import pytest

from bob3.cost_telemetry_guardian import (
    CostFloorResult,
    enforce_cost_floor_on_zero_report,
)


class TestTelemetryLossDetection:
    """cost==0 AND work_events > 100 → telemetry lost → charge ceiling."""

    def test_zero_cost_high_work_events_triggers_telemetry_loss(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(20.0)

    def test_zero_cost_work_events_just_above_threshold(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="test-feature",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_none_cost_high_work_events_triggers_telemetry_loss(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=15.0,
            feature_id="test-none-cost",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(15.0)

    def test_negative_cost_high_work_events_triggers_telemetry_loss(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=-0.001,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-negative-cost",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_telemetry_lost_charges_full_ceiling_not_partial(self):
        """When telemetry is lost, the full ceiling is charged, not zero."""
        ceiling = 25.0
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=ceiling,
            feature_id="test-full-ceiling",
        )
        assert result.cost_to_charge == pytest.approx(ceiling)


class TestFreeRetryPath:
    """cost==0 AND work_events==0 → genuine spawn crash → free retry."""

    def test_zero_cost_zero_work_is_free_retry(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="test-free-retry",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_none_cost_zero_work_is_free_retry(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="test-none-free-retry",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_zero_cost_at_threshold_is_not_telemetry_loss(self):
        """work_events == threshold (100) → NOT telemetry loss (strictly greater)."""
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="test-at-threshold",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)


class TestNormalCostPassthrough:
    """cost > 0 → normal case, returned as-is."""

    def test_positive_cost_returned_unchanged(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=5.50,
            work_events=200,
            per_feature_ceiling=20.0,
            feature_id="test-normal-cost",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(5.50)

    def test_small_positive_cost_returned_unchanged(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.001,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="test-small-positive",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.001)

    def test_positive_cost_zero_work_events_returned_unchanged(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=3.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="test-positive-cost-zero-work",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(3.0)


class TestReturnType:
    """enforce_cost_floor_on_zero_report returns CostFloorResult."""

    def test_returns_cost_floor_result_instance(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="test-return-type",
        )
        assert isinstance(result, CostFloorResult)

    def test_cost_to_charge_is_float(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-float-type",
        )
        assert isinstance(result.cost_to_charge, float)

    def test_telemetry_lost_is_bool(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-bool-type",
        )
        assert isinstance(result.telemetry_lost, bool)


class TestInvalidCeilingRaises:
    """Invalid per_feature_ceiling raises ValueError."""

    def test_zero_ceiling_raises_value_error(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_cost_floor_on_zero_report(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id="test-zero-ceiling",
            )

    def test_negative_ceiling_raises_value_error(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_cost_floor_on_zero_report(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-5.0,
                feature_id="test-negative-ceiling",
            )

    @pytest.mark.parametrize("bad_ceiling", [0.0, -0.001, -1.0, -10.0])
    def test_all_non_positive_ceilings_raise(self, bad_ceiling):
        with pytest.raises(ValueError):
            enforce_cost_floor_on_zero_report(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=bad_ceiling,
                feature_id="test-param-bad-ceiling",
            )


class TestOptionalParameters:
    """Optional parameters (exit_code, attempt_number) have correct defaults."""

    def test_default_exit_code_none(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-default-exit",
        )
        assert isinstance(result, CostFloorResult)

    def test_explicit_exit_code(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-explicit-exit",
            exit_code=1,
        )
        assert isinstance(result, CostFloorResult)
        assert result.telemetry_lost is True

    def test_attempt_number_param(self):
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-attempt-3",
            attempt_number=3,
        )
        assert isinstance(result, CostFloorResult)
        assert result.telemetry_lost is True


class TestCrashScenarioFromSpec:
    """Reproduce the exact scenario from the feature spec (feature 9b2e1060)."""

    def test_spec_crash_scenario(self):
        """cost=0, work_events=176217, exit_code=1 → telemetry lost → ceiling charged."""
        result = enforce_cost_floor_on_zero_report(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(20.0)
        assert result.cost_to_charge > 0.0, (
            "Zero cost MUST NOT disable budget enforcement; ceiling must be charged"
        )
