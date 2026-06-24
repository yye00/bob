"""Tests for feature da0085c2: zero-reported-cost MUST NOT disable budget enforcement.

Verifies zero_reported_cost_must_not_disable_budget_enforcement behavior:
- zero cost + high work_events → pessimistic ceiling applied (telemetry_lost=True)
- zero cost + zero work_events → genuine spawn crash, cost 0.0 returned (telemetry_lost=False)
- nonzero cost → reported cost returned unmodified (telemetry_lost=False)
- emit cost_telemetry_lost WARN log when telemetry is detected lost
- threshold boundary conditions respected
"""

from __future__ import annotations

import logging

import pytest

from bob.zero_reported_cost_must_not_disable_budget_enforcement import (
    ZeroCostEnforcementResult,
    zero_reported_cost_must_not_disable_budget_enforcement,
)


FEATURE_ID = "da0085c2-test-feature"
CEILING = 5.00


def test_zero_reported_cost_must_not_disable_budget_enforcement():
    """Core AC test: zero cost + high work_events MUST apply ceiling, not disable enforcement."""
    result = zero_reported_cost_must_not_disable_budget_enforcement(
        reported_cost=0.0,
        work_events=176217,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
        exit_code=1,
        attempt_number=1,
    )
    assert isinstance(result, ZeroCostEnforcementResult)
    assert result.telemetry_lost is True, (
        "Zero cost + high work_events must be classified as telemetry lost, "
        "not as 'no budget to enforce'"
    )
    assert result.cost_to_charge == pytest.approx(CEILING), (
        "When telemetry is lost, per_feature_ceiling must be charged "
        "to preserve budget enforcement"
    )


class TestZeroCostEnforcementCoreInvariants:
    """Verify the three-way design invariant."""

    def test_zero_cost_high_work_applies_ceiling(self):
        """Zero cost + 176217 work_events → ceiling applied (telemetry_lost=True)."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_zero_cost_zero_work_free_retry_path(self):
        """Zero cost + zero work_events → genuine spawn crash, charge 0.0."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_nonzero_cost_returned_unmodified(self):
        """Positive cost → reported cost returned unchanged."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=1.23,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(1.23)

    def test_none_cost_high_work_treated_as_zero(self):
        """None cost coerced to 0.0; high work_events → ceiling applied."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_negative_cost_treated_as_zero_with_high_work(self):
        """Negative cost coerced to 0.0; high work_events → ceiling applied."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=-0.5,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)


class TestThresholdBoundary:
    """Verify threshold boundary conditions (default=100, exclusive upper bound)."""

    def test_threshold_boundary_above(self):
        """work_events=101 (> default 100) → telemetry_lost=True."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True

    def test_threshold_boundary_at_default(self):
        """work_events=100 (== default, not >) → telemetry_lost=False."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False

    def test_threshold_boundary_below(self):
        """work_events=99 (< default 100) → telemetry_lost=False."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False

    def test_env_threshold_override(self, monkeypatch):
        """BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD env var is respected."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=51,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True

    def test_env_threshold_at_boundary(self, monkeypatch):
        """With threshold=50, work_events=50 is NOT lost (threshold is exclusive)."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False


class TestLogging:
    """Verify structured cost_telemetry_lost WARN log events."""

    def test_emits_warn_log_when_telemetry_lost(self, caplog):
        """Structured cost_telemetry_lost WARN log emitted when telemetry is detected lost."""
        with caplog.at_level(logging.WARNING):
            zero_reported_cost_must_not_disable_budget_enforcement(
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

    def test_no_log_on_genuine_spawn_crash(self, caplog):
        """No cost_telemetry_lost log emitted for genuine spawn crash (work_events=0)."""
        with caplog.at_level(logging.WARNING):
            zero_reported_cost_must_not_disable_budget_enforcement(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
            )
        assert not any("cost_telemetry_lost" in r.message for r in caplog.records)

    def test_attempt_number_in_log(self, caplog):
        """attempt_number is included in the structured log message."""
        with caplog.at_level(logging.WARNING):
            zero_reported_cost_must_not_disable_budget_enforcement(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
                attempt_number=7,
            )
        warn_record = next(r for r in caplog.records if "cost_telemetry_lost" in r.message)
        assert "7" in warn_record.message


class TestReturnType:
    """Verify the result object structure."""

    def test_returns_zero_cost_enforcement_result(self):
        """Return type is ZeroCostEnforcementResult."""
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, ZeroCostEnforcementResult)
        assert hasattr(result, "cost_to_charge")
        assert hasattr(result, "telemetry_lost")

    def test_ceiling_charged_equals_per_feature_ceiling(self):
        """When telemetry lost, cost_to_charge equals exact per_feature_ceiling passed."""
        ceiling = 12.75
        result = zero_reported_cost_must_not_disable_budget_enforcement(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=ceiling,
            feature_id=FEATURE_ID,
        )
        assert result.cost_to_charge == pytest.approx(ceiling)
