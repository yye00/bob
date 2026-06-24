"""Tests for zero_reported_cost_must_not_disable_budget_enforcement feature.

Covers the invariant: cost==0 AND work_events > threshold MUST charge the
per-feature ceiling and log cost_telemetry_lost, never disable enforcement.
"""

import logging

import pytest

from bob3.zero_reported_cost_must_not_disable_budget_enforcement_stream_json_telemetry_miss_currently_flips_safety_net_off_enabling_runaway_subagent_burn_under_crash_conditions import (
    zero_reported_cost_must_not_disable_budget_enforcement_stream_json_telemetry_miss_currently_flips_safety_net_off_enabling_runaway_subagent_burn_under_crash_conditions as enforce_fn,
)

FEATURE_ID = "9b2e1060-test"
CEILING = 5.0


def _call(reported_cost, work_events, ceiling=CEILING, feature_id=FEATURE_ID,
           exit_code=1, attempt=1):
    return enforce_fn(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt,
    )


def test_zero_reported_cost_must_not_disable_budget_enforcement_stream_json_telemetry_miss_currently_flips_safety_net_off_enabling_runaway_subagent_burn_under_crash_conditions():
    """Core AC test: high work_events + zero cost → ceiling charged, telemetry_lost=True."""
    result = _call(reported_cost=0.0, work_events=176217)
    assert result.telemetry_lost is True, "telemetry_lost must be True when cost==0 and work_events high"
    assert result.cost_to_charge == CEILING, (
        f"cost_to_charge must equal the ceiling {CEILING}, got {result.cost_to_charge}"
    )


def test_genuine_spawn_crash_zero_work_zero_cost():
    """cost==0 AND work_events==0 → free retry, NOT a telemetry loss."""
    result = _call(reported_cost=0.0, work_events=0)
    assert result.telemetry_lost is False
    assert result.cost_to_charge == 0.0


def test_normal_positive_cost_returned_as_is():
    """cost > 0 → normal path, returned unchanged."""
    result = _call(reported_cost=2.5, work_events=1000)
    assert result.telemetry_lost is False
    assert result.cost_to_charge == pytest.approx(2.5)


def test_none_cost_treated_as_zero_with_high_work_events():
    """None cost treated as 0.0; high work_events → ceiling applied."""
    result = _call(reported_cost=None, work_events=500)
    assert result.telemetry_lost is True
    assert result.cost_to_charge == CEILING


def test_work_events_at_threshold_boundary_is_not_lost():
    """work_events == threshold (100) does NOT trigger telemetry-loss."""
    result = _call(reported_cost=0.0, work_events=100)
    assert result.telemetry_lost is False
    assert result.cost_to_charge == 0.0


def test_work_events_just_above_threshold_triggers_loss():
    """work_events == threshold+1 DOES trigger telemetry-loss."""
    result = _call(reported_cost=0.0, work_events=101)
    assert result.telemetry_lost is True
    assert result.cost_to_charge == CEILING


def test_cost_telemetry_lost_event_is_logged(caplog):
    """Structured cost_telemetry_lost WARN event is emitted."""
    with caplog.at_level(logging.WARNING):
        _call(reported_cost=0.0, work_events=176217, feature_id="feat-abc", exit_code=1, attempt=3)
    assert any("cost_telemetry_lost" in r.message for r in caplog.records), (
        "Expected a log record containing 'cost_telemetry_lost'"
    )


def test_cost_telemetry_lost_event_not_emitted_for_normal_cost(caplog):
    """No cost_telemetry_lost event when cost > 0."""
    with caplog.at_level(logging.WARNING):
        _call(reported_cost=1.23, work_events=50000)
    assert not any("cost_telemetry_lost" in r.message for r in caplog.records)


def test_negative_cost_treated_as_zero_high_work_events():
    """Negative cost is coerced to 0.0; high work_events → ceiling applied."""
    result = _call(reported_cost=-0.01, work_events=200)
    assert result.telemetry_lost is True
    assert result.cost_to_charge == CEILING


def test_ceiling_applied_equals_per_feature_ceiling():
    """cost_to_charge equals the exact ceiling passed in."""
    custom_ceiling = 12.75
    result = _call(reported_cost=0.0, work_events=99999, ceiling=custom_ceiling)
    assert result.cost_to_charge == pytest.approx(custom_ceiling)


def test_result_attributes_exist():
    """Result object exposes cost_to_charge and telemetry_lost attributes."""
    result = _call(reported_cost=0.0, work_events=200)
    assert hasattr(result, "cost_to_charge")
    assert hasattr(result, "telemetry_lost")
