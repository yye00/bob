"""Tests for bob3.run_loop budget enforcement functions.

AC: pytest: tests/test_run_loop_budget_enforcement.py
AC: integration: bob3.run_loop

Verifies:
- handle_zero_cost_with_work_events is importable from bob3.run_loop
- log_cost_telemetry_lost is importable from bob3.run_loop
- Core behavior: zero cost + high work_events → ceiling applied (telemetry_lost=True)
- Core behavior: zero cost + zero work_events → free-retry path (telemetry_lost=False)
- Core behavior: nonzero cost → returned as-is (telemetry_lost=False)
- log_cost_telemetry_lost emits a WARN log with cost_telemetry_lost
- Integration: both functions live in bob3.run_loop module
"""

from __future__ import annotations

import logging

import pytest

import bob3.run_loop as run_loop_module
from bob3.run_loop import handle_zero_cost_with_work_events, log_cost_telemetry_lost


FEATURE_ID = "test-budget-enforcement-8a51641e"
CEILING = 5.00


class TestHandleZeroCostWithWorkEventsIntegration:
    """Verify the function exists in bob3.run_loop and is callable."""

    def test_importable_from_bob3_run_loop(self):
        assert hasattr(run_loop_module, "handle_zero_cost_with_work_events"), (
            "handle_zero_cost_with_work_events must be exported from bob3.run_loop"
        )

    def test_log_cost_telemetry_lost_importable(self):
        assert hasattr(run_loop_module, "log_cost_telemetry_lost"), (
            "log_cost_telemetry_lost must be exported from bob3.run_loop"
        )

    def test_both_in_all(self):
        assert "handle_zero_cost_with_work_events" in run_loop_module.__all__
        assert "log_cost_telemetry_lost" in run_loop_module.__all__


class TestHandleZeroCostWithWorkEventsCore:
    """Core behavioral tests for handle_zero_cost_with_work_events."""

    def test_zero_cost_high_work_applies_ceiling(self):
        """Zero cost + 176217 work_events → ceiling applied (telemetry_lost=True)."""
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
            exit_code=1,
            attempt_number=1,
        )
        assert result["telemetry_lost"] is True, (
            "Zero cost + high work_events must be classified as telemetry lost"
        )
        assert result["effective_cost"] == pytest.approx(CEILING), (
            "When telemetry is lost, per_feature_ceiling must be charged"
        )

    def test_zero_cost_zero_work_free_retry(self):
        """Zero cost + zero work_events → genuine spawn crash → effective_cost=0.0."""
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result["telemetry_lost"] is False, (
            "Zero cost + zero work_events is a genuine spawn crash, not telemetry loss"
        )
        assert result["effective_cost"] == pytest.approx(0.0)

    def test_nonzero_cost_returned_as_is(self):
        """Nonzero reported cost → returned unchanged (telemetry_lost=False)."""
        result = handle_zero_cost_with_work_events(
            reported_cost=2.50,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result["telemetry_lost"] is False
        assert result["effective_cost"] == pytest.approx(2.50)

    def test_returns_dict_with_required_keys(self):
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert "effective_cost" in result
        assert "telemetry_lost" in result
        assert isinstance(result["effective_cost"], float)
        assert isinstance(result["telemetry_lost"], bool)

    def test_none_cost_high_work_treated_as_zero(self):
        """None cost is coerced to 0.0; high work_events triggers telemetry loss."""
        result = handle_zero_cost_with_work_events(
            reported_cost=None,
            work_events=500,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result["telemetry_lost"] is True
        assert result["effective_cost"] == pytest.approx(CEILING)

    def test_threshold_boundary_at_100_no_telemetry_loss(self):
        """work_events == 100 is exactly at threshold (not above) → no telemetry loss."""
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result["telemetry_lost"] is False
        assert result["effective_cost"] == pytest.approx(0.0)

    def test_threshold_boundary_at_101_triggers_telemetry_loss(self):
        """work_events == 101 is one above threshold → telemetry loss detected."""
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
        assert result["telemetry_lost"] is True
        assert result["effective_cost"] == pytest.approx(CEILING)

    def test_budget_enforcement_not_disabled_on_zero_cost(self):
        """Core invariant: zero cost MUST NOT disable budget enforcement."""
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id=FEATURE_ID,
        )
        # enforcement is active: ceiling was charged, not bypassed
        assert result["effective_cost"] > 0.0, (
            "Budget enforcement must not be disabled on zero-reported-cost with high work_events"
        )

    def test_different_ceilings_are_respected(self):
        """The ceiling applied matches the per_feature_ceiling argument."""
        for ceiling in [1.0, 5.0, 10.0, 20.0]:
            result = handle_zero_cost_with_work_events(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=ceiling,
                feature_id=FEATURE_ID,
            )
            assert result["effective_cost"] == pytest.approx(ceiling)


class TestLogCostTelemetryLost:
    """Tests for the log_cost_telemetry_lost function in bob3.run_loop."""

    def test_emits_warn_log(self, caplog):
        """log_cost_telemetry_lost must emit a WARN-level log entry."""
        with caplog.at_level(logging.WARNING):
            log_cost_telemetry_lost(
                feature_id=FEATURE_ID,
                work_events=176217,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=5.0,
            )
        assert any(
            record.levelno >= logging.WARNING for record in caplog.records
        ), "log_cost_telemetry_lost must emit at least one WARNING-level log"

    def test_log_contains_cost_telemetry_lost_marker(self, caplog):
        """Log message must contain the 'cost_telemetry_lost' marker string."""
        with caplog.at_level(logging.WARNING):
            log_cost_telemetry_lost(
                feature_id=FEATURE_ID,
                work_events=176217,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=5.0,
            )
        full_log = " ".join(record.getMessage() for record in caplog.records)
        assert "cost_telemetry_lost" in full_log, (
            "Log output must contain 'cost_telemetry_lost' for grep-ability"
        )

    def test_log_includes_feature_id(self, caplog):
        """Log must include the feature_id for traceability."""
        fid = "trace-feature-test-id"
        with caplog.at_level(logging.WARNING):
            log_cost_telemetry_lost(
                feature_id=fid,
                work_events=1000,
                exit_code=1,
                attempt_number=2,
                applied_pessimistic_cost=10.0,
            )
        full_log = " ".join(record.getMessage() for record in caplog.records)
        assert fid in full_log

    def test_log_returns_none(self):
        """log_cost_telemetry_lost must return None (it is a side-effect function)."""
        result = log_cost_telemetry_lost(
            feature_id=FEATURE_ID,
            work_events=500,
            exit_code=0,
            attempt_number=1,
            applied_pessimistic_cost=5.0,
        )
        assert result is None

    def test_none_exit_code_accepted(self):
        """None exit_code must not raise."""
        log_cost_telemetry_lost(
            feature_id=FEATURE_ID,
            work_events=200,
            exit_code=None,
            attempt_number=1,
            applied_pessimistic_cost=5.0,
        )


class TestRunLoopBudgetEnforcementIntegration:
    """Integration tests: bob3.run_loop exposes the correct enforcement interface."""

    def test_handle_zero_cost_with_work_events_callable(self):
        fn = getattr(run_loop_module, "handle_zero_cost_with_work_events", None)
        assert callable(fn)

    def test_log_cost_telemetry_lost_callable(self):
        fn = getattr(run_loop_module, "log_cost_telemetry_lost", None)
        assert callable(fn)

    def test_typical_crash_scenario(self):
        """Simulate the original bug: feature 9b2e1060, work_events=176217, cost=0, exit=1."""
        result = handle_zero_cost_with_work_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060-simulated",
            exit_code=1,
            attempt_number=1,
        )
        assert result["telemetry_lost"] is True, (
            "The original bug: cost=0 + 176K events was NOT telemetry loss — "
            "this test proves the fix prevents disabling enforcement"
        )
        assert result["effective_cost"] == pytest.approx(20.0)
