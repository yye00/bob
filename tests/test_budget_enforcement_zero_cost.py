"""Tests for feature 6845fe77: zero-reported-cost MUST NOT disable budget enforcement.

Verifies enforce_budget_with_cost_telemetry_fallback behavior:
- zero cost + high work_events → pessimistic ceiling applied (telemetry_lost=True)
- zero cost + zero work_events → genuine spawn crash, cost 0.0 returned (telemetry_lost=False)
- nonzero cost → reported cost returned unmodified (telemetry_lost=False)
- function is importable from bob.orchestrator directly
"""

from __future__ import annotations

import logging
import os

import pytest

import bob.orchestrator
from bob.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult,
    enforce_budget_with_cost_telemetry_fallback,
)


FEATURE_ID = "test-feature-zero-cost"
CEILING = 5.00


class TestEnforceBudgetWithCostTelemetryFallback:
    """Core behavioral tests for enforce_budget_with_cost_telemetry_fallback."""

    def test_zero_cost_high_work_applies_ceiling(self):
        """Zero cost + 176217 work_events → ceiling applied (telemetry_lost=True)."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, EnforceBudgetResult)
        assert result.telemetry_lost is True
        assert result.cost_to_charge == CEILING

    def test_zero_cost_zero_work_free_retry_path(self):
        """Zero cost + zero work_events → genuine spawn crash, charge 0.0 (telemetry_lost=False)."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == 0.0

    def test_nonzero_cost_returned_unmodified(self):
        """Positive cost → cost returned unchanged, no ceiling applied."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=1.23,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(1.23)

    def test_none_cost_high_work_events_treated_as_zero(self):
        """None cost coerced to 0.0; high work_events → ceiling applied."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == CEILING

    def test_negative_cost_treated_as_zero_with_high_work(self):
        """Negative cost coerced to 0.0; high work_events → ceiling applied."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=-0.5,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == CEILING

    def test_threshold_boundary_at_101(self):
        """work_events=101 (> default 100) → telemetry_lost=True."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True

    def test_threshold_boundary_at_100(self):
        """work_events=100 (== default, not >) → telemetry_lost=False."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False

    def test_threshold_boundary_at_99(self):
        """work_events=99 (< default 100) → telemetry_lost=False."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False

    def test_ceiling_applied_equals_per_feature_ceiling(self):
        """When telemetry lost, cost_to_charge equals the exact per_feature_ceiling passed."""
        ceiling = 12.75
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=ceiling,
            feature_id=FEATURE_ID,
        )
        assert result.cost_to_charge == pytest.approx(ceiling)

    def test_returns_enforce_budget_result_type(self):
        """Return type is EnforceBudgetResult with the expected slots."""
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert hasattr(result, "cost_to_charge")
        assert hasattr(result, "telemetry_lost")

    def test_emits_warn_log_when_telemetry_lost(self, caplog):
        """Structured cost_telemetry_lost WARN log emitted when telemetry is detected lost."""
        with caplog.at_level(logging.WARNING):
            enforce_budget_with_cost_telemetry_fallback(
                reported_cost=0.0,
                work_events=176217,
                per_feature_ceiling=CEILING,
                feature_id="test-9b2e1060",
                exit_code=1,
                attempt_number=3,
            )
        assert any("cost_telemetry_lost" in r.message for r in caplog.records)
        warn_record = next(r for r in caplog.records if "cost_telemetry_lost" in r.message)
        assert "test-9b2e1060" in warn_record.message
        assert "176217" in warn_record.message

    def test_no_warn_log_on_clean_spawn_crash(self, caplog):
        """No cost_telemetry_lost log emitted for genuine spawn crash (work_events=0)."""
        with caplog.at_level(logging.WARNING):
            enforce_budget_with_cost_telemetry_fallback(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
            )
        assert not any("cost_telemetry_lost" in r.message for r in caplog.records)

    def test_attempt_number_forwarded_to_log(self, caplog):
        """attempt_number is included in the structured log message."""
        with caplog.at_level(logging.WARNING):
            enforce_budget_with_cost_telemetry_fallback(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
                attempt_number=7,
            )
        warn_record = next(r for r in caplog.records if "cost_telemetry_lost" in r.message)
        assert "7" in warn_record.message

    def test_env_threshold_override(self, monkeypatch):
        """BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD env var is respected."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=51,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True

    def test_env_threshold_override_below_boundary(self, monkeypatch):
        """With threshold=50, work_events=50 is NOT lost (threshold is exclusive)."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = enforce_budget_with_cost_telemetry_fallback(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False


class TestBobOrchestratorIntegration:
    """Verify enforce_budget_with_cost_telemetry_fallback is exported from bob.orchestrator."""

    def test_function_importable_from_orchestrator_package(self):
        """enforce_budget_with_cost_telemetry_fallback accessible via bob.orchestrator."""
        fn = getattr(bob.orchestrator, "enforce_budget_with_cost_telemetry_fallback", None)
        assert fn is not None, (
            "enforce_budget_with_cost_telemetry_fallback not found in bob.orchestrator"
        )
        assert callable(fn)

    def test_orchestrator_import_returns_same_function(self):
        """Function imported from bob.orchestrator is identical to direct import."""
        from bob.orchestrator import enforce_budget_with_cost_telemetry_fallback as via_pkg
        assert via_pkg is enforce_budget_with_cost_telemetry_fallback

    def test_orchestrator_function_works_end_to_end(self):
        """Function callable via bob.orchestrator namespace produces correct result."""
        from bob.orchestrator import enforce_budget_with_cost_telemetry_fallback as fn
        result = fn(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=3.50,
            feature_id="integration-test-9b2e1060",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(3.50)
