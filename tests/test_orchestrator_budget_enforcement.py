"""7ac9cc81: Budget enforcement on zero-reported-cost (stream-json telemetry miss).

Tests for bob.orchestrator.enforce_budget_on_zero_cost — the unified entry
point that prevents zero-cost from disabling budget enforcement.

Design invariant being tested:
- cost==0 AND work_events > threshold → TELEMETRY LOST → charge ceiling, emit event
- cost==0 AND work_events == 0       → CLEAN SPAWN CRASH → charge 0.0, no event
- cost > 0                           → NORMAL → charge reported cost, no event
"""

from __future__ import annotations

import logging

import pytest

from bob.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult,
    enforce_budget_on_zero_cost,
    enforce_budget_with_telemetry_loss,
)
from bob.orchestrator import enforce_budget_on_zero_cost as enforce_from_pkg
from bob.orchestrator import enforce_budget_with_telemetry_loss as enforce_with_telemetry_loss_from_pkg


class TestEnforceBudgetOnZeroCostImport:
    """enforce_budget_on_zero_cost is importable from bob.orchestrator."""

    def test_importable_from_orchestrator_package(self):
        """AC: bob.orchestrator.enforce_budget_on_zero_cost is importable."""
        assert callable(enforce_from_pkg)

    def test_same_object_as_module_level(self):
        """Package export and module-level function are the same object."""
        from bob.orchestrator.cost_telemetry_guard import enforce_budget_on_zero_cost as direct
        assert enforce_from_pkg is direct


class TestEnforceBudgetResultType:
    """EnforceBudgetResult has the expected interface."""

    def test_has_cost_to_charge(self):
        result = enforce_budget_on_zero_cost(
            reported_cost=1.0,
            work_events=50,
            per_feature_ceiling=5.0,
            feature_id="feat-typecheck",
        )
        assert hasattr(result, "cost_to_charge")

    def test_has_telemetry_lost(self):
        result = enforce_budget_on_zero_cost(
            reported_cost=1.0,
            work_events=50,
            per_feature_ceiling=5.0,
            feature_id="feat-typecheck",
        )
        assert hasattr(result, "telemetry_lost")

    def test_returns_enforce_budget_result_instance(self):
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=200,
            per_feature_ceiling=5.0,
            feature_id="feat-type",
        )
        assert isinstance(result, EnforceBudgetResult)


class TestTelemetryLostPath:
    """cost==0, work_events > threshold → pessimistic ceiling charged."""

    def test_incident_scenario_zero_cost_176k_events(self):
        """AC: the observed incident (cost=0, work_events=176217) charges ceiling."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(20.0)

    def test_telemetry_lost_charges_ceiling_not_zero(self):
        """Budget enforcement stays ON when telemetry is lost."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=5000,
            per_feature_ceiling=15.0,
            feature_id="feat-lost",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge > 0.0
        assert result.cost_to_charge == pytest.approx(15.0)

    def test_none_cost_high_work_events_lost(self):
        """None reported_cost (SDK omission) with high work_events → lost."""
        result = enforce_budget_on_zero_cost(
            reported_cost=None,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="feat-none",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_negative_cost_high_work_events_lost(self):
        """Negative cost (invalid SDK value) treated as 0 → detected as lost."""
        result = enforce_budget_on_zero_cost(
            reported_cost=-1.5,
            work_events=300,
            per_feature_ceiling=8.0,
            feature_id="feat-neg",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(8.0)

    def test_telemetry_lost_emits_warn_event(self, caplog):
        """When telemetry is lost, a cost_telemetry_lost WARN log is emitted."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            enforce_budget_on_zero_cost(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=5.0,
                feature_id="feat-warn",
                exit_code=1,
                attempt_number=2,
            )
        warn_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("cost_telemetry_lost" in m for m in warn_msgs)

    def test_telemetry_lost_event_contains_feature_id(self, caplog):
        """cost_telemetry_lost event log contains the feature_id."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            enforce_budget_on_zero_cost(
                reported_cost=0.0,
                work_events=150,
                per_feature_ceiling=5.0,
                feature_id="feat-id-check-abc",
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "feat-id-check-abc" in log_text

    def test_telemetry_lost_event_contains_work_events(self, caplog):
        """cost_telemetry_lost log contains the work_events count."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            enforce_budget_on_zero_cost(
                reported_cost=0.0,
                work_events=88888,
                per_feature_ceiling=5.0,
                feature_id="feat-we",
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "88888" in log_text


class TestCleanSpawnCrashPath:
    """cost==0, work_events==0 → genuine spawn crash → charge 0.0, no event."""

    def test_zero_cost_zero_events_not_lost(self):
        """AC: (cost=0, work_events=0) → telemetry_lost=False, cost_to_charge=0.0."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="feat-crash",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == 0.0

    def test_zero_cost_zero_events_no_warn_emitted(self, caplog):
        """Clean spawn crash does NOT emit cost_telemetry_lost event."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            enforce_budget_on_zero_cost(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=20.0,
                feature_id="feat-no-warn",
            )
        warn_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("cost_telemetry_lost" in m for m in warn_msgs)

    def test_none_cost_zero_events_clean_crash(self):
        """None cost, zero work_events → clean crash, no enforcement penalty."""
        result = enforce_budget_on_zero_cost(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=5.0,
            feature_id="feat-none-crash",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == 0.0


class TestNormalCostPath:
    """cost > 0 → normal case, reported cost returned unchanged."""

    def test_positive_cost_returned_as_is(self):
        """Normal run returns reported cost without modification."""
        result = enforce_budget_on_zero_cost(
            reported_cost=2.75,
            work_events=1000,
            per_feature_ceiling=20.0,
            feature_id="feat-normal",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(2.75)

    def test_small_positive_cost_not_treated_as_lost(self):
        """Any positive cost means telemetry arrived; enforcement uses exact cost."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0001,
            work_events=500000,
            per_feature_ceiling=20.0,
            feature_id="feat-small",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(0.0001)

    def test_large_positive_cost_returned(self):
        """Large cost is returned verbatim."""
        result = enforce_budget_on_zero_cost(
            reported_cost=18.99,
            work_events=50000,
            per_feature_ceiling=20.0,
            feature_id="feat-large",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == pytest.approx(18.99)

    def test_normal_cost_no_warn_emitted(self, caplog):
        """Normal (positive) cost path does not emit cost_telemetry_lost event."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            enforce_budget_on_zero_cost(
                reported_cost=1.23,
                work_events=200,
                per_feature_ceiling=5.0,
                feature_id="feat-no-event",
            )
        warn_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("cost_telemetry_lost" in m for m in warn_msgs)


class TestThresholdBoundary:
    """Boundary conditions around the default threshold of 100 work events."""

    def test_work_events_at_threshold_not_lost(self):
        """work_events == 100 (not >) → NOT lost."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=5.0,
            feature_id="feat-boundary",
        )
        assert result.telemetry_lost is False
        assert result.cost_to_charge == 0.0

    def test_work_events_just_above_threshold_is_lost(self):
        """work_events == 101 (> 100) → lost."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=5.0,
            feature_id="feat-boundary-above",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(5.0)

    def test_custom_threshold_via_env(self, monkeypatch):
        """BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD env var shifts the boundary."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=51,
            per_feature_ceiling=10.0,
            feature_id="feat-custom-thresh",
        )
        assert result.telemetry_lost is True
        assert result.cost_to_charge == pytest.approx(10.0)

    def test_custom_threshold_boundary_not_lost(self, monkeypatch):
        """At custom threshold (not >) → NOT lost."""
        monkeypatch.setenv("BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD", "50")
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id="feat-custom-boundary",
        )
        assert result.telemetry_lost is False


class TestOptionalParameters:
    """exit_code and attempt_number are optional and default gracefully."""

    def test_defaults_for_optional_params(self, caplog):
        """Calling without exit_code/attempt_number does not raise."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            result = enforce_budget_on_zero_cost(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=5.0,
                feature_id="feat-defaults",
            )
        assert result.telemetry_lost is True
        assert len(caplog.records) >= 1

    def test_none_exit_code_does_not_raise(self, caplog):
        """None exit_code is allowed and does not crash the event emitter."""
        with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
            result = enforce_budget_on_zero_cost(
                reported_cost=0.0,
                work_events=300,
                per_feature_ceiling=5.0,
                feature_id="feat-none-exit",
                exit_code=None,
                attempt_number=1,
            )
        assert result.telemetry_lost is True


class TestBudgetEnforcementNeverDisabled:
    """Core invariant: zero-cost NEVER disables budget enforcement when work was done."""

    def test_zero_cost_does_not_return_zero_when_work_done(self):
        """Zero reported cost + work done → ceiling charged, NOT zero (not disabled)."""
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=10000,
            per_feature_ceiling=20.0,
            feature_id="feat-invariant",
        )
        # If this returns 0.0 budget enforcement would be disabled — must be > 0
        assert result.cost_to_charge > 0.0

    def test_ceiling_applied_not_intermediate_value(self):
        """When telemetry is lost the FULL ceiling is applied (conservative charge)."""
        ceiling = 25.0
        result = enforce_budget_on_zero_cost(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=ceiling,
            feature_id="feat-full-ceiling",
        )
        assert result.cost_to_charge == pytest.approx(ceiling)


# --- AC tests for feature 52623df9-67ac-457c-9a7c-2a8823f8b02c ---
# enforce_budget_with_telemetry_loss must be importable from bob.orchestrator
# and implement the same three-path logic as enforce_budget_on_zero_cost.


def test_zero_cost_with_work_events_enforces_ceiling():
    """AC: zero-cost + high work_events → ceiling enforced (NEVER disabled).

    When reported cost is 0 but work_events exceeds the threshold, the
    orchestrator MUST apply the per-feature ceiling rather than treating
    zero-cost as "no budget to enforce".
    """
    result = enforce_budget_with_telemetry_loss(
        reported_cost=0.0,
        work_events=176217,
        per_feature_ceiling=20.0,
        feature_id="9b2e1060",
        exit_code=1,
        attempt_number=1,
    )
    assert result.telemetry_lost is True
    assert result.cost_to_charge == pytest.approx(20.0), (
        "Budget enforcement must charge per-feature ceiling when telemetry is lost"
    )
    # Also verify it's callable from bob.orchestrator package namespace
    assert callable(enforce_with_telemetry_loss_from_pkg)


def test_zero_cost_zero_work_events_allows_free_retry():
    """AC: zero-cost + zero work_events → genuine spawn crash → free retry.

    When both cost and work_events are zero, this is a genuine spawn-time
    crash (F-R7-478 path). Budget enforcement must NOT charge the ceiling;
    the effective cost must remain 0.0 so the free-retry path fires.
    """
    result = enforce_budget_with_telemetry_loss(
        reported_cost=0.0,
        work_events=0,
        per_feature_ceiling=20.0,
        feature_id="feat-spawn-crash",
        exit_code=1,
        attempt_number=1,
    )
    assert result.telemetry_lost is False
    assert result.cost_to_charge == 0.0, (
        "Genuine spawn crash (zero work events) must not charge ceiling"
    )


def test_cost_telemetry_lost_event_logged(caplog):
    """AC: cost_telemetry_lost structured event is emitted when telemetry is lost.

    When zero-cost + high work_events triggers the telemetry-loss path,
    a structured log event containing 'cost_telemetry_lost' MUST be emitted
    at WARNING level so operators can grep for it in incident response.
    """
    with caplog.at_level(logging.WARNING, logger="bob.orchestrator.cost_telemetry_guard"):
        enforce_budget_with_telemetry_loss(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="feat-event-check",
            exit_code=1,
            attempt_number=1,
        )
    warn_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("cost_telemetry_lost" in m for m in warn_msgs), (
        "cost_telemetry_lost structured event must appear in WARNING logs"
    )
