"""Boundary-case tests: zero, empty, or minimum inputs to cost enforcement functions.

AC: pytest: tests/test_zero_reported_cost_must_not_disable_budget_enforce_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising.

Covers:
- validate_reported_cost with zero/None/minimum inputs
- enforce_zero_cost_policy with zero/None/minimum inputs
- should_treat_cost_as_unknown with boundary values
- validate_cost_and_events with boundary values
"""

from __future__ import annotations

import pytest

from bob3.cost_enforcement import (
    CostValidationResult,
    enforce_zero_cost_policy,
    should_treat_cost_as_unknown,
    validate_cost_and_events,
    validate_reported_cost,
)


class TestBoundaryZeroCostZeroWork:
    """Zero cost + zero work_events → free-retry path, no exception."""

    def test_validate_reported_cost_zero_zero(self):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-zero-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_validate_reported_cost_none_zero(self):
        result = validate_reported_cost(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-none-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_enforce_zero_cost_policy_zero_zero(self):
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-enforce-zero-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert isinstance(result.effective_cost, float)

    def test_enforce_zero_cost_policy_none_zero(self):
        result = enforce_zero_cost_policy(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-enforce-none-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert isinstance(result.effective_cost, float)
        assert isinstance(result.telemetry_lost, bool)


class TestBoundaryMinimumWorkEvents:
    """Minimum work_events values around the default threshold of 100."""

    def test_work_events_one(self):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=1,
            per_feature_ceiling=10.0,
            feature_id="boundary-work-one",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False

    def test_work_events_at_threshold(self):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="boundary-work-at-threshold",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_work_events_one_above_threshold(self):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="boundary-work-one-above-threshold",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(10.0)

    def test_should_treat_cost_as_unknown_at_threshold(self):
        result = should_treat_cost_as_unknown(reported_cost=0.0, work_events=100)
        assert isinstance(result, bool)
        assert result is False

    def test_should_treat_cost_as_unknown_one_below_threshold(self):
        result = should_treat_cost_as_unknown(reported_cost=0.0, work_events=99)
        assert isinstance(result, bool)
        assert result is False

    def test_should_treat_cost_as_unknown_one_above_threshold(self):
        result = should_treat_cost_as_unknown(reported_cost=0.0, work_events=101)
        assert isinstance(result, bool)
        assert result is True


class TestBoundaryMinimumCeiling:
    """Minimal positive ceiling (epsilon) should produce a well-defined result."""

    def test_very_small_ceiling(self):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=0.0001,
            feature_id="boundary-small-ceiling",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(0.0001)

    def test_enforce_zero_cost_policy_very_small_ceiling(self):
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=0.0001,
            feature_id="boundary-enforce-small-ceiling",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is True


class TestBoundaryValidateCostAndEvents:
    """validate_cost_and_events boundary inputs return well-defined results."""

    def test_zero_cost_zero_work(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-vce-zero-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_none_cost_zero_work(self):
        result = validate_cost_and_events(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-vce-none-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False

    def test_zero_cost_at_threshold(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="boundary-vce-at-threshold",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False

    def test_zero_cost_one_above_threshold(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="boundary-vce-one-above",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(10.0)


class TestBoundaryReturnTypes:
    """All boundary inputs return consistent types (not None, not exception)."""

    @pytest.mark.parametrize("work_events", [0, 1, 50, 100, 101, 1000])
    def test_validate_reported_cost_returns_result_type(self, work_events):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=work_events,
            per_feature_ceiling=10.0,
            feature_id="boundary-return-type",
        )
        assert isinstance(result, CostValidationResult)
        assert isinstance(result.effective_cost, float)
        assert isinstance(result.telemetry_lost, bool)

    @pytest.mark.parametrize("reported_cost", [None, 0.0, -0.001, 0.0001, 5.0])
    def test_validate_reported_cost_various_cost_values(self, reported_cost):
        result = validate_reported_cost(
            reported_cost=reported_cost,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id="boundary-various-costs",
        )
        assert isinstance(result, CostValidationResult)
        assert isinstance(result.effective_cost, float)
        assert isinstance(result.telemetry_lost, bool)
