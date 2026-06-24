"""Tests for 789ac06d: zero-reported-cost MUST NOT disable budget enforcement.

AC1: Function defined: bob.orchestrator.enforce_budget_on_zero_cost_with_work_events
AC2: File exists: src/bob/cost_telemetry.py
AC3: pytest: tests/test_cost_telemetry_enforcement.py (this file)
AC4: integration: bob.orchestrator (function importable from the package)

Design invariant enforced here:
- cost==0 AND work_events > threshold → telemetry lost → apply ceiling
- cost==0 AND work_events == 0 → genuine spawn-crash → cost remains 0 (free retry)
- cost > 0 → normal → returned as-is
"""

from __future__ import annotations

import importlib
import os

import pytest

from bob.cost_telemetry import (
    enforce_budget_on_zero_cost_with_work_events,
    EnforceBudgetWithWorkEventsResult,
)


# ---------------------------------------------------------------------------
# AC 1 & 4 — importability from both bob.cost_telemetry and bob.orchestrator
# ---------------------------------------------------------------------------


class TestImportability:
    """The function must be importable from bob.orchestrator (integration AC)."""

    def test_importable_from_bob_orchestrator(self):
        """AC4: bob.orchestrator exposes enforce_budget_on_zero_cost_with_work_events."""
        mod = importlib.import_module("bob.orchestrator")
        func = getattr(mod, "enforce_budget_on_zero_cost_with_work_events", None)
        assert func is not None, (
            "enforce_budget_on_zero_cost_with_work_events not found in bob.orchestrator"
        )

    def test_importable_from_bob_cost_telemetry(self):
        """AC2: bob.cost_telemetry module exists and exposes the function."""
        mod = importlib.import_module("bob.cost_telemetry")
        func = getattr(mod, "enforce_budget_on_zero_cost_with_work_events", None)
        assert func is not None

    def test_result_class_importable(self):
        """EnforceBudgetWithWorkEventsResult is a named type, not a bare tuple."""
        assert EnforceBudgetWithWorkEventsResult is not None


# ---------------------------------------------------------------------------
# Core behavior: telemetry-loss detection path
# ---------------------------------------------------------------------------


class TestTelemetryLossPath:
    """cost==0 AND work_events > threshold → pessimistic ceiling applied."""

    def test_observational_case_176k_events(self):
        """Reproduces the actual incident: feature 9b2e1060, work_events=176217."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060-0000-0000-0000-000000000000",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(20.0)

    def test_ceiling_applied_not_reported_cost(self):
        """When telemetry is lost, cost_to_charge equals per_feature_ceiling, not 0."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=15.0,
            feature_id="aaaa-bbbb",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(15.0)

    def test_just_above_threshold_triggers_detection(self):
        """work_events=101 (default threshold=100) → telemetry lost."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="test-feature",
        )
        assert result.telemetry_lost is True

    def test_none_cost_treated_as_zero(self):
        """None reported_cost is coerced to 0.0 — still triggers detection when work_events > threshold."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=None,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-feature",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_negative_cost_treated_as_zero(self):
        """Negative cost (bad SDK value) → coerced to 0.0; triggers detection."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=-1.5,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="test-feature",
        )
        assert result.telemetry_lost is True


# ---------------------------------------------------------------------------
# Free-retry path: cost==0 AND work_events == 0
# ---------------------------------------------------------------------------


class TestFreeRetryPath:
    """Genuine spawn-crash (zero work done) MUST NOT be penalised as telemetry loss."""

    def test_zero_cost_zero_work_is_not_telemetry_loss(self):
        """(cost=0, work_events=0) → telemetry_lost=False, cost_to_charge=0.0."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="spawn-crash-feature",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_none_cost_zero_work_is_not_telemetry_loss(self):
        """None cost + zero work → genuine spawn crash, not telemetry loss."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="spawn-crash-feature",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_exactly_at_threshold_not_detected(self):
        """work_events == 100 (= threshold, NOT >) → NOT telemetry loss."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="boundary-feature",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_below_threshold_not_detected(self):
        """work_events=99 < default threshold 100 → NOT telemetry loss."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=10.0,
            feature_id="below-threshold-feature",
        )
        assert result.telemetry_lost is False


# ---------------------------------------------------------------------------
# Normal (positive cost) path
# ---------------------------------------------------------------------------


class TestNormalCostPath:
    """Positive cost: returned as-is, no telemetry-loss classification."""

    def test_positive_cost_returned_unchanged(self):
        """When cost > 0, cost_to_charge equals reported cost."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=3.14,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="normal-feature",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(3.14)

    def test_small_positive_cost_not_detected_as_lost(self):
        """Very small positive cost still means telemetry arrived."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0001,
            work_events=200000,
            per_feature_ceiling=20.0,
            feature_id="small-cost-feature",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0001)

    def test_large_positive_cost_unchanged(self):
        """Large positive costs pass through without ceiling being applied."""
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=8.75,
            work_events=50000,
            per_feature_ceiling=20.0,
            feature_id="large-cost-feature",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(8.75)


# ---------------------------------------------------------------------------
# Threshold env var override
# ---------------------------------------------------------------------------


class TestThresholdEnvVar:
    """BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD overrides the default threshold."""

    def test_lower_threshold_triggers_earlier(self, monkeypatch):
        """Threshold=10 → work_events=50 triggers detection."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "10")
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id="threshold-env-feature",
        )
        assert result.telemetry_lost is True

    def test_higher_threshold_suppresses_detection(self, monkeypatch):
        """Threshold=1000 → work_events=176 does NOT trigger detection."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "1000")
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=176,
            per_feature_ceiling=10.0,
            feature_id="threshold-env-feature",
        )
        assert result.telemetry_lost is False

    def test_invalid_threshold_env_falls_back_to_default(self, monkeypatch):
        """Non-numeric env var falls back to default 100."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "bogus")
        # work_events=101 > default 100 → still detected
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="fallback-feature",
        )
        assert result.telemetry_lost is True


# ---------------------------------------------------------------------------
# Result type structure
# ---------------------------------------------------------------------------


class TestResultType:
    """EnforceBudgetWithWorkEventsResult has the expected attributes."""

    def test_result_has_cost_to_charge(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=5.0,
            work_events=100,
            per_feature_ceiling=20.0,
            feature_id="result-type-test",
        )
        assert hasattr(result, "cost_to_charge")

    def test_result_has_telemetry_lost(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=5.0,
            work_events=100,
            per_feature_ceiling=20.0,
            feature_id="result-type-test",
        )
        assert hasattr(result, "telemetry_lost")

    def test_result_cost_to_charge_is_float(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=3.0,
            work_events=50,
            per_feature_ceiling=20.0,
            feature_id="float-type-test",
        )
        assert isinstance(result.cost_to_charge, float)

    def test_result_telemetry_lost_is_bool(self):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=3.0,
            work_events=50,
            per_feature_ceiling=20.0,
            feature_id="bool-type-test",
        )
        assert isinstance(result.telemetry_lost, bool)


# ---------------------------------------------------------------------------
# Ceiling parametrisation
# ---------------------------------------------------------------------------


class TestCeilingValues:
    """The per_feature_ceiling is applied as the pessimistic charge."""

    @pytest.mark.parametrize("ceiling", [5.0, 10.0, 20.0, 50.0])
    def test_ceiling_applied_exactly(self, ceiling):
        result = enforce_budget_on_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=ceiling,
            feature_id="ceiling-param-test",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(ceiling)
