"""Tests for bob.cost_telemetry_validator (feature dd04e2b3).

AC: pytest: tests/test_cost_telemetry_validator.py

Verifies validate_cost_and_work_events behavior:
- cost==0 AND work_events > threshold → ceiling charged, telemetry_lost=True
- cost==0 AND work_events == 0 → free-retry, cost=0.0, telemetry_lost=False
- cost > 0 → reported cost returned as-is, telemetry_lost=False
- None cost coerced to 0.0
- Structured cost_telemetry_lost WARN log emitted when telemetry is lost
- ValueError raised for invalid (non-positive) per_feature_ceiling
"""

from __future__ import annotations

import logging

import pytest

from bob.cost_telemetry_validator import (
    CostTelemetryValidationResult,
    validate_cost_and_work_events,
)

FEATURE_ID = "dd04e2b3-test-feature"
CEILING = 5.00


class TestCoreInvariants:
    """Verify the three-way design invariant of validate_cost_and_work_events."""

    def test_zero_cost_high_work_events_applies_ceiling(self):
        """Zero cost + high work_events → telemetry lost → ceiling charged."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
            exit_code=1,
            attempt_number=1,
        )
        assert isinstance(result, CostTelemetryValidationResult)
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_zero_cost_zero_work_events_free_retry(self):
        """Zero cost + zero work_events → genuine spawn crash, cost=0.0."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_nonzero_cost_returned_as_is(self):
        """Positive cost → returned unchanged, telemetry_lost=False."""
        result = validate_cost_and_work_events(
            reported_cost=2.75,
            work_events=1000,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(2.75)

    def test_none_cost_high_work_events_treated_as_telemetry_loss(self):
        """None cost coerced to 0.0; high work_events → ceiling applied."""
        result = validate_cost_and_work_events(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_negative_cost_treated_as_zero_high_work(self):
        """Negative cost coerced to 0.0; high work_events → ceiling applied."""
        result = validate_cost_and_work_events(
            reported_cost=-1.5,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)


class TestThresholdBoundaries:
    """Verify work_events threshold boundary conditions (default=100, exclusive)."""

    def test_threshold_at_default_not_lost(self):
        """work_events=100 (== default threshold, not >) → telemetry_lost=False."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0)

    def test_threshold_one_above_default_triggers_loss(self):
        """work_events=101 (> default 100) → telemetry_lost=True."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(CEILING)

    def test_threshold_one_below_default_not_lost(self):
        """work_events=99 (< default 100) → telemetry_lost=False."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False

    def test_env_threshold_override_triggers_loss(self, monkeypatch):
        """BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD env var is respected."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=51,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is True

    def test_env_threshold_at_boundary_not_lost(self, monkeypatch):
        """With threshold=50, work_events=50 is NOT lost (exclusive upper bound)."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result.telemetry_lost is False


class TestLogging:
    """Verify structured cost_telemetry_lost WARN log events."""

    def test_emits_warn_log_on_telemetry_loss(self, caplog):
        """cost_telemetry_lost WARN event is emitted when loss detected."""
        with caplog.at_level(logging.WARNING):
            validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=176217,
                per_feature_ceiling=CEILING,
                feature_id="test-9b2e1060",
                exit_code=1,
                attempt_number=2,
            )
        assert any("cost_telemetry_lost" in r.message for r in caplog.records)
        warn_record = next(r for r in caplog.records if "cost_telemetry_lost" in r.message)
        assert "test-9b2e1060" in warn_record.message
        assert "176217" in warn_record.message

    def test_no_log_on_genuine_spawn_crash(self, caplog):
        """No cost_telemetry_lost log emitted for genuine spawn crash (work_events=0)."""
        with caplog.at_level(logging.WARNING):
            validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
            )
        assert not any("cost_telemetry_lost" in r.message for r in caplog.records)

    def test_no_log_on_normal_cost(self, caplog):
        """No cost_telemetry_lost log emitted for normal positive cost."""
        with caplog.at_level(logging.WARNING):
            validate_cost_and_work_events(
                reported_cost=1.5,
                work_events=500,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
            )
        assert not any("cost_telemetry_lost" in r.message for r in caplog.records)

    def test_attempt_number_in_log(self, caplog):
        """attempt_number is included in the structured log message."""
        with caplog.at_level(logging.WARNING):
            validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=CEILING,
                feature_id=FEATURE_ID,
                attempt_number=5,
            )
        warn_record = next(r for r in caplog.records if "cost_telemetry_lost" in r.message)
        assert "5" in warn_record.message


class TestReturnType:
    """Verify the result object structure and type correctness."""

    def test_returns_cost_telemetry_validation_result(self):
        """Return type is CostTelemetryValidationResult."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result, CostTelemetryValidationResult)
        assert hasattr(result, "cost_to_charge")
        assert hasattr(result, "telemetry_lost")

    def test_cost_to_charge_is_float(self):
        """cost_to_charge attribute is always a float."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result.cost_to_charge, float)

    def test_telemetry_lost_is_bool(self):
        """telemetry_lost attribute is always a bool."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert isinstance(result.telemetry_lost, bool)

    def test_ceiling_exact_value_applied(self):
        """When telemetry lost, cost_to_charge equals exact per_feature_ceiling passed."""
        ceiling = 12.75
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=ceiling,
            feature_id=FEATURE_ID,
        )
        assert result.cost_to_charge == pytest.approx(ceiling)


class TestInvalidInputRaises:
    """Invalid per_feature_ceiling must raise ValueError, not silently succeed."""

    def test_zero_ceiling_raises_value_error(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id=FEATURE_ID,
            )

    def test_negative_ceiling_raises_value_error(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-5.0,
                feature_id=FEATURE_ID,
            )

    @pytest.mark.parametrize("bad_ceiling", [0.0, -0.001, -1.0, -10.0])
    def test_all_invalid_ceilings_raise(self, bad_ceiling):
        with pytest.raises(ValueError):
            validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=bad_ceiling,
                feature_id=FEATURE_ID,
            )

    def test_invalid_ceiling_does_not_silently_succeed(self):
        """Invalid ceiling must raise — not return a result silently."""
        result = None
        try:
            result = validate_cost_and_work_events(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id=FEATURE_ID,
            )
        except ValueError:
            pass
        assert result is None, "validate_cost_and_work_events must NOT return a value for invalid ceiling"


class TestIncidentReproduction:
    """Reproduces the exact incident: feature 9b2e1060 crash scenario."""

    def test_incident_9b2e1060_zero_cost_high_work(self):
        """Incident reproduction: work_events=176217, cost=0.0, exit_code=1."""
        result = validate_cost_and_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id="9b2e1060",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True, (
            "Incident: zero cost + 176K work_events MUST be classified as telemetry loss, "
            "not as 'budget enforcement disabled'"
        )
        assert result.cost_to_charge == pytest.approx(CEILING), (
            "Incident: per_feature_ceiling must be charged to preserve budget enforcement"
        )
