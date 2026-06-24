"""Tests for enforce_zero_cost_threshold in bob3.orchestrator.

AC: Function defined: bob3.orchestrator.enforce_zero_cost_threshold
AC: pytest: tests/test_zero_cost_enforcement.py
AC: integration: bob3.orchestrator

Verifies that zero-reported-cost MUST NOT disable budget enforcement:
- enforce_zero_cost_threshold is importable from bob3.orchestrator
- telemetry-loss path (cost==0, work_events > threshold) applies ceiling charge
- free-retry path (cost==0, work_events==0) is NOT treated as telemetry loss
- normal path (cost > 0) returns cost as-is
- structured cost_telemetry_lost event is emitted on telemetry loss
"""

from __future__ import annotations

import logging

import pytest

from bob3.orchestrator import enforce_zero_cost_threshold
from bob3.cost_enforcement import CostValidationResult


class TestEnforceZeroCostThresholdImport:
    """enforce_zero_cost_threshold must be importable from bob3.orchestrator."""

    def test_function_is_callable(self):
        assert callable(enforce_zero_cost_threshold)

    def test_function_is_in_orchestrator_namespace(self):
        import bob3.orchestrator as orch
        assert hasattr(orch, "enforce_zero_cost_threshold")


class TestEnforceZeroCostThresholdTelemetryLoss:
    """cost==0 AND work_events > 100 → telemetry loss → charge ceiling."""

    def test_zero_cost_high_work_events_charges_ceiling(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=5.0,
            feature_id="test-telemetry-loss",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(5.0)

    def test_zero_cost_just_above_threshold_charges_ceiling(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=3.0,
            feature_id="test-just-above-threshold",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(3.0)

    def test_none_cost_high_work_events_charges_ceiling(self):
        result = enforce_zero_cost_threshold(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=10.0,
            feature_id="test-none-cost-high-work",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(10.0)

    def test_negative_cost_high_work_events_charges_ceiling(self):
        result = enforce_zero_cost_threshold(
            reported_cost=-0.01,
            work_events=200,
            per_feature_ceiling=7.5,
            feature_id="test-negative-cost-high-work",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(7.5)

    def test_emits_warning_log_on_telemetry_loss(self, caplog):
        with caplog.at_level(logging.WARNING):
            enforce_zero_cost_threshold(
                reported_cost=0.0,
                work_events=150,
                per_feature_ceiling=5.0,
                feature_id="test-log-emission",
            )
        assert any("cost_telemetry_lost" in r.message for r in caplog.records)


class TestEnforceZeroCostThresholdFreeRetryPath:
    """cost==0 AND work_events==0 → genuine spawn crash → cost=0.0, not telemetry loss."""

    def test_zero_cost_zero_work_is_not_telemetry_loss(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=5.0,
            feature_id="test-free-retry",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_none_cost_zero_work_is_not_telemetry_loss(self):
        result = enforce_zero_cost_threshold(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=5.0,
            feature_id="test-none-free-retry",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_zero_cost_at_threshold_is_not_telemetry_loss(self):
        """work_events == threshold (100) does NOT trigger telemetry loss — must exceed it."""
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=5.0,
            feature_id="test-at-threshold",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)


class TestEnforceZeroCostThresholdNormalPath:
    """cost > 0 → normal path → returned as-is."""

    def test_positive_cost_returned_unchanged(self):
        result = enforce_zero_cost_threshold(
            reported_cost=1.23,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id="test-normal-cost",
        )
        assert isinstance(result, CostValidationResult)
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(1.23)

    def test_small_positive_cost_returned_unchanged(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.001,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-small-positive-cost",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.001)

    def test_large_positive_cost_returned_unchanged(self):
        result = enforce_zero_cost_threshold(
            reported_cost=99.99,
            work_events=176217,
            per_feature_ceiling=5.0,
            feature_id="test-large-cost",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(99.99)


class TestEnforceZeroCostThresholdReturnType:
    """enforce_zero_cost_threshold must always return a CostValidationResult."""

    @pytest.mark.parametrize(
        "reported_cost,work_events",
        [
            (0.0, 0),
            (0.0, 50),
            (0.0, 100),
            (0.0, 101),
            (0.0, 176217),
            (None, 0),
            (None, 500),
            (1.5, 0),
            (1.5, 500),
        ],
    )
    def test_always_returns_cost_validation_result(self, reported_cost, work_events):
        result = enforce_zero_cost_threshold(
            reported_cost=reported_cost,
            work_events=work_events,
            per_feature_ceiling=5.0,
            feature_id="test-return-type",
        )
        assert isinstance(result, CostValidationResult)
        assert isinstance(result.effective_cost, float)
        assert isinstance(result.telemetry_lost, bool)


class TestEnforceZeroCostThresholdCeilingApplication:
    """When telemetry is lost, the exact ceiling is charged."""

    @pytest.mark.parametrize("ceiling", [0.5, 1.0, 2.5, 10.0, 100.0])
    def test_ceiling_applied_when_telemetry_lost(self, ceiling):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=ceiling,
            feature_id="test-ceiling",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(ceiling)


class TestEnforceZeroCostThresholdOptionalParams:
    """Optional parameters (exit_code, attempt_number) are accepted without error."""

    def test_with_exit_code(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=5.0,
            feature_id="test-exit-code",
            exit_code=1,
        )
        assert isinstance(result, CostValidationResult)

    def test_with_none_exit_code(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=5.0,
            feature_id="test-none-exit-code",
            exit_code=None,
        )
        assert isinstance(result, CostValidationResult)

    def test_with_attempt_number(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=5.0,
            feature_id="test-attempt-number",
            attempt_number=3,
        )
        assert isinstance(result, CostValidationResult)

    def test_with_all_params(self):
        result = enforce_zero_cost_threshold(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=5.0,
            feature_id="9b2e1060",
            exit_code=1,
            attempt_number=2,
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(5.0)
