"""Tests for feature 89efbb84: zero-reported-cost MUST NOT disable budget enforcement.

AC: pytest: tests/test_budget_enforcement.py::test_zero_cost_with_high_work_events_enforces_ceiling
AC: pytest: tests/test_budget_enforcement.py::test_zero_cost_zero_work_events_remains_free

Verifies that:
- zero cost + high work_events (>100) → pessimistic ceiling applied (telemetry lost)
- zero cost + zero work_events → free retry path, cost 0.0 (genuine spawn crash)
- bob3.orchestrator.enforce_budget_on_zero_cost is importable and callable
- Invalid input (empty/zero/None cost) returns well-defined results
- Invalid per_feature_ceiling raises ValueError
"""

from __future__ import annotations

import logging

import pytest

import bob3.orchestrator
from bob3.orchestrator import enforce_budget_on_zero_cost
from bob3.orchestrator.cost_telemetry_guard import EnforceBudgetResult


FEATURE_ID = "89efbb84-d1f5-4efd-b3ea-07bd4ae51cc6"
CEILING = 10.00


# --- Primary AC test functions ---

def test_zero_cost_with_high_work_events_enforces_ceiling():
    """AC: zero cost + work_events > 100 → ceiling applied, telemetry_lost=True.

    Replicates the failure observed in bob3 v.15 r12 (2026-05-29):
    feature 9b2e1060 crashed with work_events=176217, exit_code=1, reported
    cost=0. The fix must treat this as telemetry loss and charge the ceiling.
    """
    result = enforce_budget_on_zero_cost(
        reported_cost=0.0,
        work_events=176217,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
        exit_code=1,
        attempt_number=1,
    )
    assert isinstance(result, EnforceBudgetResult)
    assert result.telemetry_lost is True, (
        "work_events=176217 >> threshold=100 must trigger telemetry_lost"
    )
    assert result.cost_to_charge == pytest.approx(CEILING), (
        "cost_to_charge must equal per_feature_ceiling when telemetry is lost"
    )


def test_zero_cost_zero_work_events_remains_free():
    """AC: zero cost + zero work_events → genuine spawn crash, charge 0.0.

    F-R7-478 free-retry path: when a sub-agent crashes before doing any
    work, the zero cost is legitimate. Budget enforcement remains active
    (no ceiling applied) and cost_to_charge=0.0.
    """
    result = enforce_budget_on_zero_cost(
        reported_cost=0.0,
        work_events=0,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
        exit_code=1,
        attempt_number=1,
    )
    assert isinstance(result, EnforceBudgetResult)
    assert result.telemetry_lost is False, (
        "work_events=0 is a genuine spawn crash, NOT telemetry loss"
    )
    assert result.cost_to_charge == pytest.approx(0.0), (
        "genuine spawn crash must be free (cost_to_charge=0.0)"
    )


# --- Integration AC: enforce_budget_on_zero_cost in bob3.orchestrator ---

def test_enforce_budget_on_zero_cost_importable_from_orchestrator():
    """AC: Function defined: bob3.orchestrator.enforce_budget_on_zero_cost."""
    fn = getattr(bob3.orchestrator, "enforce_budget_on_zero_cost", None)
    assert fn is not None, "enforce_budget_on_zero_cost not found in bob3.orchestrator"
    assert callable(fn)


def test_enforce_budget_on_zero_cost_callable_from_orchestrator_namespace():
    """Function accessible via bob3.orchestrator namespace works end-to-end."""
    fn = bob3.orchestrator.enforce_budget_on_zero_cost
    result = fn(
        reported_cost=0.0,
        work_events=500,
        per_feature_ceiling=7.50,
        feature_id="integration-test-89efbb84",
    )
    assert result.telemetry_lost is True
    assert result.cost_to_charge == pytest.approx(7.50)


# --- Behavior AC: empty/zero/None input returns well-defined result ---

def test_none_reported_cost_high_work_events_enforces_ceiling():
    """AC behavior: empty or zero input returns well-defined result (not crash).

    None cost is coerced to 0.0; combined with high work_events → ceiling applied.
    """
    result = enforce_budget_on_zero_cost(
        reported_cost=None,
        work_events=200,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
    )
    assert isinstance(result, EnforceBudgetResult)
    assert result.telemetry_lost is True
    assert result.cost_to_charge == pytest.approx(CEILING)


def test_zero_cost_none_work_returns_well_defined_result():
    """AC behavior: zero cost with 0 work_events returns defined result (no crash)."""
    result = enforce_budget_on_zero_cost(
        reported_cost=0.0,
        work_events=0,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
    )
    assert isinstance(result, EnforceBudgetResult)
    assert result.cost_to_charge == 0.0
    assert result.telemetry_lost is False


def test_positive_cost_returned_as_is():
    """AC behavior: positive reported cost passes through unchanged."""
    result = enforce_budget_on_zero_cost(
        reported_cost=3.14,
        work_events=176217,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
    )
    assert result.telemetry_lost is False
    assert result.cost_to_charge == pytest.approx(3.14)


# --- Behavior AC: invalid input raises ValueError ---

def test_invalid_input_negative_ceiling_raises_value_error():
    """AC behavior: invalid input raises ValueError and does not silently succeed.

    enforce_budget_on_zero_cost delegates to lower-level primitives; the
    named entry point in bob3.cost_enforcement.enforce_zero_cost_policy is the
    canonical ValueError raiser. Here we verify via orchestrator proxy.
    """
    from bob3.orchestrator import enforce_zero_cost_policy
    with pytest.raises(ValueError):
        enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=-1.0,
            feature_id=FEATURE_ID,
        )


def test_invalid_input_zero_ceiling_raises_value_error():
    """AC behavior: zero per_feature_ceiling raises ValueError."""
    from bob3.orchestrator import enforce_zero_cost_policy
    with pytest.raises(ValueError):
        enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=0.0,
            feature_id=FEATURE_ID,
        )


# --- Threshold boundary tests ---

def test_threshold_boundary_at_101():
    """work_events=101 (> default 100) → telemetry_lost=True."""
    result = enforce_budget_on_zero_cost(
        reported_cost=0.0,
        work_events=101,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
    )
    assert result.telemetry_lost is True


def test_threshold_boundary_at_100():
    """work_events=100 (== default, not >) → telemetry_lost=False."""
    result = enforce_budget_on_zero_cost(
        reported_cost=0.0,
        work_events=100,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
    )
    assert result.telemetry_lost is False


def test_threshold_boundary_at_99():
    """work_events=99 (< default 100) → telemetry_lost=False."""
    result = enforce_budget_on_zero_cost(
        reported_cost=0.0,
        work_events=99,
        per_feature_ceiling=CEILING,
        feature_id=FEATURE_ID,
    )
    assert result.telemetry_lost is False


def test_cost_telemetry_lost_warn_log_emitted(caplog):
    """Structured cost_telemetry_lost WARN log emitted when telemetry is lost."""
    with caplog.at_level(logging.WARNING):
        enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=CEILING,
            feature_id="log-test-feature-89efbb84",
            exit_code=1,
            attempt_number=2,
        )
    assert any("cost_telemetry_lost" in r.message for r in caplog.records)


def test_no_warn_log_for_genuine_spawn_crash(caplog):
    """No cost_telemetry_lost log emitted for genuine spawn crash (work_events=0)."""
    with caplog.at_level(logging.WARNING):
        enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=CEILING,
            feature_id=FEATURE_ID,
        )
    assert not any("cost_telemetry_lost" in r.message for r in caplog.records)
