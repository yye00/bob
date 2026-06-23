"""Tests for 354499d7: zero-reported-cost MUST NOT disable budget enforcement.

AC: pytest: tests/test_cost_enforcement_zero_reported.py

Verifies that:
- zero cost + high work_events → pessimistic ceiling applied (telemetry lost)
- zero cost + zero work_events → genuine spawn crash, free-retry path (no charge)
- positive cost → returned as-is (normal path)
- budget enforcement NEVER disabled on zero cost + substantial work
"""

from __future__ import annotations

import logging

import pytest

from orchestrator.cost_enforcement import enforce_cost_ceiling


FEATURE_ID = "354499d7-6e45-4a3f-838e-a9f6160be1b6"
CEILING = 20.0


class TestZeroCostTelemetryLoss:
    """Zero cost + high work_events must apply ceiling, not disable enforcement."""

    def test_incident_reproduction_176k_events(self):
        """Reproduce actual incident: work_events=176217, exit_code=1, cost=0."""
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
            exit_code=1,
            attempt_number=1,
        )
        assert result == pytest.approx(CEILING), (
            "Zero cost + 176k work_events must apply ceiling, not return 0"
        )

    def test_zero_cost_high_work_applies_ceiling(self):
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=15.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(15.0)

    def test_budget_enforcement_not_disabled_on_zero_cost(self):
        """MUST NOT return 0.0 (enforcement disabled) when work_events > threshold."""
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result > 0.0, "Budget enforcement must not be disabled on zero cost + high events"

    def test_none_cost_treated_as_zero_with_high_events(self):
        result = enforce_cost_ceiling(
            reported_cost=None,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(10.0)

    def test_negative_cost_treated_as_zero_with_high_events(self):
        result = enforce_cost_ceiling(
            reported_cost=-1.5,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(10.0)

    def test_just_above_threshold_triggers_ceiling(self):
        """work_events=101 (default threshold=100) → ceiling applied."""
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(10.0)

    def test_emits_warning_log_on_telemetry_loss(self, caplog):
        with caplog.at_level(logging.WARNING):
            enforce_cost_ceiling(
                reported_cost=0.0,
                work_events=176217,
                per_feature_ceiling=20.0,
                feature_id=FEATURE_ID,
                exit_code=1,
                attempt_number=1,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "cost_telemetry_lost" in log_text


class TestGenuineSpawnCrash:
    """Zero cost + zero work_events → genuine spawn crash (free retry path)."""

    def test_zero_cost_zero_work_free_retry(self):
        """F-R7-478 path: spawn crash with no work — free retry, no charge."""
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
            exit_code=1,
        )
        assert result == pytest.approx(0.0)

    def test_none_cost_zero_work_free_retry(self):
        result = enforce_cost_ceiling(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(0.0)

    def test_at_threshold_not_telemetry_loss(self):
        """work_events == 100 (threshold, not >) → free retry, not telemetry loss."""
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(0.0)


class TestNormalPositiveCost:
    """Positive reported cost → returned as-is."""

    def test_positive_cost_returned_unchanged(self):
        result = enforce_cost_ceiling(
            reported_cost=3.14,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(3.14)

    def test_small_positive_cost_not_affected(self):
        result = enforce_cost_ceiling(
            reported_cost=0.0001,
            work_events=200000,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(0.0001)


class TestInvalidCeiling:
    """Invalid ceiling raises ValueError — enforcement cannot operate without positive ceiling."""

    def test_zero_ceiling_raises(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_cost_ceiling(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id=FEATURE_ID,
            )

    def test_negative_ceiling_raises(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_cost_ceiling(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-5.0,
                feature_id=FEATURE_ID,
            )


class TestThresholdEnvOverride:
    """BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD overrides default threshold of 100."""

    def test_lower_threshold_triggers_earlier(self, monkeypatch):
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "10")
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(10.0)

    def test_higher_threshold_allows_smaller_work_events(self, monkeypatch):
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "1000")
        result = enforce_cost_ceiling(
            reported_cost=0.0,
            work_events=176,
            per_feature_ceiling=10.0,
            feature_id=FEATURE_ID,
        )
        assert result == pytest.approx(0.0)
