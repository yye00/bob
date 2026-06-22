"""Tests for fbe6b19b: pessimistic cost application on lost telemetry.

Covers apply_pessimistic_cost and emit_cost_telemetry_lost_event from
bob3.orchestrator.cost_telemetry_guard.

Key AC assertions:
- apply_pessimistic_cost returns per-feature ceiling when telemetry is lost
- apply_pessimistic_cost returns reported cost when telemetry is NOT lost
- emit_cost_telemetry_lost_event writes a WARN-level structured log line
  with feature_id, work_events, exit_code, attempt_number, applied_pessimistic_cost
"""

from __future__ import annotations

import logging

import pytest

from bob3.orchestrator.cost_telemetry_guard import (
    apply_pessimistic_cost,
    emit_cost_telemetry_lost_event,
    is_cost_telemetry_lost,
)


class TestApplyPessimisticCost:
    """apply_pessimistic_cost returns ceiling on lost telemetry, reported cost otherwise."""

    def test_lost_telemetry_returns_ceiling(self):
        """AC: apply_pessimistic_cost charges per-feature ceiling on lost telemetry."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=5.0,
        )
        assert result == 5.0

    def test_not_lost_returns_reported_cost(self):
        """AC: apply_pessimistic_cost returns reported cost when not lost."""
        result = apply_pessimistic_cost(
            reported_cost=1.23,
            is_lost=False,
            per_feature_ceiling=5.0,
        )
        assert result == pytest.approx(1.23)

    def test_not_lost_zero_work_events_returns_zero(self):
        """Clean spawn crash (work_events=0, cost=0) → not lost → cost returned as-is (0.0)."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=False,
            per_feature_ceiling=5.0,
        )
        assert result == 0.0

    def test_lost_with_large_ceiling(self):
        """Ceiling can be any positive float."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=99.99,
        )
        assert result == pytest.approx(99.99)

    def test_lost_with_zero_ceiling_returns_zero(self):
        """Edge: ceiling=0.0 (no budget set) → 0.0 returned (enforcement still fires, just charges 0)."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=0.0,
        )
        assert result == 0.0

    def test_not_lost_large_reported_cost_returned(self):
        """Not-lost path always returns the reported cost, even if it's large."""
        result = apply_pessimistic_cost(
            reported_cost=42.0,
            is_lost=False,
            per_feature_ceiling=5.0,
        )
        assert result == pytest.approx(42.0)

    def test_lost_ignores_reported_cost(self):
        """When lost, the reported_cost is irrelevant — ceiling is always returned."""
        result = apply_pessimistic_cost(
            reported_cost=0.123,  # some non-zero noise, shouldn't matter
            is_lost=True,
            per_feature_ceiling=3.0,
        )
        assert result == pytest.approx(3.0)


class TestEmitCostTelemetryLostEvent:
    """emit_cost_telemetry_lost_event writes a structured WARN log line."""

    def test_emits_warn_level_log(self, caplog):
        """Event is logged at WARNING level."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-abc",
                work_events=176217,
                exit_code=1,
                attempt_number=2,
                applied_pessimistic_cost=5.0,
            )
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) >= 1

    def test_log_contains_feature_id(self, caplog):
        """Log message contains the feature_id."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-xyz-123",
                work_events=1000,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=2.5,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "feat-xyz-123" in log_text

    def test_log_contains_work_events(self, caplog):
        """Log message contains the work_events count."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-001",
                work_events=99999,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=1.5,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "99999" in log_text

    def test_log_contains_exit_code(self, caplog):
        """Log message contains the exit_code."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-002",
                work_events=500,
                exit_code=137,
                attempt_number=3,
                applied_pessimistic_cost=1.5,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "137" in log_text

    def test_log_contains_attempt_number(self, caplog):
        """Log message contains the attempt_number."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-003",
                work_events=200,
                exit_code=1,
                attempt_number=7,
                applied_pessimistic_cost=5.0,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "7" in log_text

    def test_log_contains_applied_pessimistic_cost(self, caplog):
        """Log message contains the applied_pessimistic_cost."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-004",
                work_events=150,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=12.34,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "12.34" in log_text or "12.3" in log_text

    def test_log_event_key_in_message(self, caplog):
        """Log message includes the 'cost_telemetry_lost' event key for grep-ability."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-005",
                work_events=300,
                exit_code=1,
                attempt_number=2,
                applied_pessimistic_cost=3.0,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "cost_telemetry_lost" in log_text

    def test_none_exit_code_handled(self, caplog):
        """None exit_code does not raise; logged as-is."""
        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="feat-006",
                work_events=200,
                exit_code=None,
                attempt_number=1,
                applied_pessimistic_cost=5.0,
            )
        # Should not raise and should emit a log record
        assert len(caplog.records) >= 1


class TestEndToEndIntegration:
    """Integration test: is_cost_telemetry_lost → apply_pessimistic_cost → emit_event."""

    def test_full_lost_telemetry_flow(self, caplog):
        """Simulate the observed incident: cost=0, work_events=176217."""
        reported_cost = 0.0
        work_events = 176217
        ceiling = 5.0

        is_lost = is_cost_telemetry_lost(reported_cost=reported_cost, work_events=work_events)
        assert is_lost is True

        applied = apply_pessimistic_cost(
            reported_cost=reported_cost,
            is_lost=is_lost,
            per_feature_ceiling=ceiling,
        )
        assert applied == pytest.approx(ceiling)

        with caplog.at_level(logging.WARNING, logger="bob3.orchestrator.cost_telemetry_guard"):
            emit_cost_telemetry_lost_event(
                feature_id="9b2e1060",
                work_events=work_events,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=applied,
            )
        assert len(caplog.records) >= 1
        assert "cost_telemetry_lost" in " ".join(r.getMessage() for r in caplog.records)

    def test_full_clean_spawn_crash_flow(self):
        """Simulate clean spawn crash: cost=0, work_events=0 → NOT lost → free retry."""
        reported_cost = 0.0
        work_events = 0
        ceiling = 5.0

        is_lost = is_cost_telemetry_lost(reported_cost=reported_cost, work_events=work_events)
        assert is_lost is False

        applied = apply_pessimistic_cost(
            reported_cost=reported_cost,
            is_lost=is_lost,
            per_feature_ceiling=ceiling,
        )
        # Not lost → return reported cost (0.0), leaving the F-R7-478 free-retry path intact
        assert applied == 0.0
