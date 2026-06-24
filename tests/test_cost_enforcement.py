"""Tests for b621f23b: zero-reported-cost MUST NOT disable budget enforcement.

Covers:
- bob3.cost_enforcement.validate_reported_cost
- bob3.cost_enforcement.log_cost_telemetry_lost
- integration: bob3.orchestrator exposes validate_reported_cost and log_cost_telemetry_lost

Design invariant:
- cost==0 AND work_events > threshold → telemetry_lost=True, effective_cost=per_feature_ceiling
- cost==0 AND work_events == 0 → telemetry_lost=False, effective_cost=0.0 (free retry path)
- cost > 0 → normal → telemetry_lost=False, effective_cost=reported_cost
- MUST NOT disable budget enforcement when cost==0 and substantial work was done
"""

from __future__ import annotations

import importlib
import logging

import pytest

from bob3.cost_enforcement import (
    validate_reported_cost,
    log_cost_telemetry_lost,
    CostValidationResult,
    validate_cost_and_events,
    should_treat_cost_as_unknown,
    enforce_zero_cost_policy,
)


# ---------------------------------------------------------------------------
# AC 2 & 3 — function existence and importability
# ---------------------------------------------------------------------------


class TestImportability:
    """Both functions must be importable from bob3.cost_enforcement."""

    def test_validate_reported_cost_importable(self):
        mod = importlib.import_module("bob3.cost_enforcement")
        assert callable(getattr(mod, "validate_reported_cost", None))

    def test_log_cost_telemetry_lost_importable(self):
        mod = importlib.import_module("bob3.cost_enforcement")
        assert callable(getattr(mod, "log_cost_telemetry_lost", None))

    def test_result_type_importable(self):
        from bob3.cost_enforcement import CostValidationResult
        assert CostValidationResult is not None


# ---------------------------------------------------------------------------
# AC 5 — integration: bob3.orchestrator exposes both functions
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    """AC5: both functions must be accessible from bob3.orchestrator."""

    def test_validate_reported_cost_in_orchestrator(self):
        mod = importlib.import_module("bob3.orchestrator")
        assert callable(getattr(mod, "validate_reported_cost", None)), (
            "validate_reported_cost not found in bob3.orchestrator"
        )

    def test_log_cost_telemetry_lost_in_orchestrator(self):
        mod = importlib.import_module("bob3.orchestrator")
        assert callable(getattr(mod, "log_cost_telemetry_lost", None)), (
            "log_cost_telemetry_lost not found in bob3.orchestrator"
        )


# ---------------------------------------------------------------------------
# validate_reported_cost: telemetry-loss detection path
# ---------------------------------------------------------------------------


class TestValidateReportedCostTelemetryLoss:
    """cost==0 AND work_events > threshold → telemetry_lost=True, apply ceiling."""

    def test_observational_case_176k_events(self):
        """Reproduces the actual incident: feature 9b2e1060, work_events=176217."""
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060-0000-0000-0000-000000000000",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(20.0)

    def test_ceiling_applied_when_telemetry_lost(self):
        """effective_cost equals per_feature_ceiling when telemetry is lost."""
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=15.0,
            feature_id="test-feature",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(15.0)

    def test_just_above_threshold_triggers_detection(self):
        """work_events=101 (default threshold=100) → telemetry_lost=True."""
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="boundary-feature",
        )
        assert result.telemetry_lost is True

    def test_none_cost_treated_as_zero(self):
        """None reported_cost coerced to 0.0 — triggers detection when work_events > threshold."""
        result = validate_reported_cost(
            reported_cost=None,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="none-cost-feature",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(10.0)

    def test_negative_cost_treated_as_zero(self):
        """Negative cost coerced to 0.0 — triggers detection."""
        result = validate_reported_cost(
            reported_cost=-1.5,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="negative-cost-feature",
        )
        assert result.telemetry_lost is True

    def test_budget_enforcement_not_disabled_on_zero_cost(self):
        """MUST NOT return effective_cost=0 when work_events > threshold."""
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id="no-disable-feature",
        )
        # Budget enforcement is preserved: effective_cost > 0
        assert result.effective_cost > 0.0


# ---------------------------------------------------------------------------
# validate_reported_cost: free-retry path (work_events == 0)
# ---------------------------------------------------------------------------


class TestValidateReportedCostFreeRetry:
    """cost==0 AND work_events == 0 → genuine spawn crash, not telemetry loss."""

    def test_zero_cost_zero_work_is_not_telemetry_loss(self):
        """F-R7-478 path: (cost=0, work_events=0) → free retry."""
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="spawn-crash-feature",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_none_cost_zero_work_is_not_telemetry_loss(self):
        result = validate_reported_cost(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="spawn-crash-none",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_exactly_at_threshold_not_detected(self):
        """work_events == 100 (= threshold, not >) → not telemetry loss."""
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=100,
            per_feature_ceiling=10.0,
            feature_id="boundary-feature",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_below_threshold_not_detected(self):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=99,
            per_feature_ceiling=10.0,
            feature_id="below-threshold",
        )
        assert result.telemetry_lost is False


# ---------------------------------------------------------------------------
# validate_reported_cost: normal (positive cost) path
# ---------------------------------------------------------------------------


class TestValidateReportedCostNormal:
    """cost > 0 → returned as-is, no ceiling applied."""

    def test_positive_cost_returned_unchanged(self):
        result = validate_reported_cost(
            reported_cost=3.14,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="normal-feature",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(3.14)

    def test_small_positive_cost_not_detected(self):
        result = validate_reported_cost(
            reported_cost=0.0001,
            work_events=200000,
            per_feature_ceiling=20.0,
            feature_id="small-cost-feature",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0001)

    def test_large_positive_cost_unchanged(self):
        result = validate_reported_cost(
            reported_cost=8.75,
            work_events=50000,
            per_feature_ceiling=20.0,
            feature_id="large-cost-feature",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(8.75)


# ---------------------------------------------------------------------------
# validate_reported_cost: threshold env var override
# ---------------------------------------------------------------------------


class TestValidateReportedCostThresholdEnvVar:
    """BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD overrides default threshold."""

    def test_lower_threshold_triggers_earlier(self, monkeypatch):
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "10")
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=50,
            per_feature_ceiling=10.0,
            feature_id="threshold-env-feature",
        )
        assert result.telemetry_lost is True

    def test_higher_threshold_suppresses_detection(self, monkeypatch):
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "1000")
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=176,
            per_feature_ceiling=10.0,
            feature_id="threshold-env-feature",
        )
        assert result.telemetry_lost is False

    def test_invalid_threshold_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "bogus")
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=101,
            per_feature_ceiling=10.0,
            feature_id="fallback-feature",
        )
        assert result.telemetry_lost is True


# ---------------------------------------------------------------------------
# CostValidationResult type
# ---------------------------------------------------------------------------


class TestCostValidationResultType:
    """CostValidationResult has required attributes with correct types."""

    def test_has_effective_cost(self):
        result = validate_reported_cost(
            reported_cost=5.0,
            work_events=100,
            per_feature_ceiling=20.0,
            feature_id="type-test",
        )
        assert hasattr(result, "effective_cost")

    def test_has_telemetry_lost(self):
        result = validate_reported_cost(
            reported_cost=5.0,
            work_events=100,
            per_feature_ceiling=20.0,
            feature_id="type-test",
        )
        assert hasattr(result, "telemetry_lost")

    def test_effective_cost_is_float(self):
        result = validate_reported_cost(
            reported_cost=3.0,
            work_events=50,
            per_feature_ceiling=20.0,
            feature_id="float-test",
        )
        assert isinstance(result.effective_cost, float)

    def test_telemetry_lost_is_bool(self):
        result = validate_reported_cost(
            reported_cost=3.0,
            work_events=50,
            per_feature_ceiling=20.0,
            feature_id="bool-test",
        )
        assert isinstance(result.telemetry_lost, bool)

    @pytest.mark.parametrize("ceiling", [5.0, 10.0, 20.0, 50.0])
    def test_ceiling_applied_exactly(self, ceiling):
        result = validate_reported_cost(
            reported_cost=0.0,
            work_events=1000,
            per_feature_ceiling=ceiling,
            feature_id="ceiling-param-test",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(ceiling)


# ---------------------------------------------------------------------------
# log_cost_telemetry_lost: structured log emission
# ---------------------------------------------------------------------------


class TestLogCostTelemetryLost:
    """log_cost_telemetry_lost emits a structured WARN log."""

    def test_emits_warning_log(self, caplog):
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            log_cost_telemetry_lost(
                feature_id="9b2e1060-0000-0000-0000-000000000000",
                work_events=176217,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=20.0,
            )
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.levelno == logging.WARNING

    def test_log_contains_feature_id(self, caplog):
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            log_cost_telemetry_lost(
                feature_id="test-feat-id-abc",
                work_events=500,
                exit_code=1,
                attempt_number=2,
                applied_pessimistic_cost=10.0,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "test-feat-id-abc" in log_text

    def test_log_contains_work_events(self, caplog):
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            log_cost_telemetry_lost(
                feature_id="feat-abc",
                work_events=176217,
                exit_code=1,
                attempt_number=1,
                applied_pessimistic_cost=15.0,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "176217" in log_text

    def test_log_contains_cost_telemetry_lost_event_key(self, caplog):
        """Log must contain cost_telemetry_lost so operators can grep for it."""
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            log_cost_telemetry_lost(
                feature_id="feat-event-key",
                work_events=200,
                exit_code=0,
                attempt_number=1,
                applied_pessimistic_cost=10.0,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "cost_telemetry_lost" in log_text

    def test_log_contains_applied_pessimistic_cost(self, caplog):
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            log_cost_telemetry_lost(
                feature_id="feat-cost-check",
                work_events=300,
                exit_code=None,
                attempt_number=3,
                applied_pessimistic_cost=25.0,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "25" in log_text

    def test_log_with_none_exit_code(self, caplog):
        """None exit_code should not cause an error."""
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            log_cost_telemetry_lost(
                feature_id="feat-none-exit",
                work_events=150,
                exit_code=None,
                attempt_number=1,
                applied_pessimistic_cost=10.0,
            )
        assert len(caplog.records) >= 1

    def test_log_returns_none(self):
        """log_cost_telemetry_lost has no return value."""
        result = log_cost_telemetry_lost(
            feature_id="feat-return-val",
            work_events=200,
            exit_code=1,
            attempt_number=1,
            applied_pessimistic_cost=10.0,
        )
        assert result is None


# ---------------------------------------------------------------------------
# validate_reported_cost emits log when telemetry is lost
# ---------------------------------------------------------------------------


class TestValidateReportedCostLogging:
    """validate_reported_cost should emit log when telemetry is lost."""

    def test_emits_log_on_telemetry_loss(self, caplog):
        with caplog.at_level(logging.WARNING):
            validate_reported_cost(
                reported_cost=0.0,
                work_events=176217,
                per_feature_ceiling=20.0,
                feature_id="log-test-feature",
                exit_code=1,
                attempt_number=1,
            )
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "cost_telemetry_lost" in log_text

    def test_no_log_on_normal_cost(self, caplog):
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            validate_reported_cost(
                reported_cost=3.14,
                work_events=176217,
                per_feature_ceiling=20.0,
                feature_id="no-log-feature",
            )
        # No warning for normal cost
        assert all(r.levelno < logging.WARNING for r in caplog.records)

    def test_no_log_on_free_retry(self, caplog):
        with caplog.at_level(logging.WARNING, logger="bob3.cost_enforcement"):
            validate_reported_cost(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=20.0,
                feature_id="free-retry-feature",
            )
        # No warning for genuine spawn crash
        assert all(r.levelno < logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# AC1: validate_cost_and_events
# ---------------------------------------------------------------------------


class TestValidateCostAndEvents:
    """validate_cost_and_events is the named AC entry point wrapping validate_reported_cost."""

    def test_importable(self):
        mod = importlib.import_module("bob3.cost_enforcement")
        assert callable(getattr(mod, "validate_cost_and_events", None))

    def test_telemetry_loss_path(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060-0000-0000-0000-000000000000",
            exit_code=1,
            attempt_number=1,
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(20.0)

    def test_free_retry_path(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="spawn-crash",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_normal_cost_path(self):
        result = validate_cost_and_events(
            reported_cost=3.14,
            work_events=5000,
            per_feature_ceiling=20.0,
            feature_id="normal-feature",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(3.14)

    def test_returns_cost_validation_result(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=15.0,
            feature_id="type-check-feature",
        )
        assert isinstance(result, CostValidationResult)

    def test_budget_not_disabled_on_high_work_events(self):
        result = validate_cost_and_events(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id="no-disable",
        )
        assert result.effective_cost > 0.0

    def test_none_cost_with_work_events(self):
        result = validate_cost_and_events(
            reported_cost=None,
            work_events=200,
            per_feature_ceiling=10.0,
            feature_id="none-cost",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(10.0)

    def test_orchestrator_integration(self):
        mod = importlib.import_module("bob3.orchestrator")
        assert callable(getattr(mod, "validate_cost_and_events", None))


# ---------------------------------------------------------------------------
# AC2: should_treat_cost_as_unknown
# ---------------------------------------------------------------------------


class TestShouldTreatCostAsUnknown:
    """should_treat_cost_as_unknown is the named AC predicate for telemetry-loss detection."""

    def test_importable(self):
        mod = importlib.import_module("bob3.cost_enforcement")
        assert callable(getattr(mod, "should_treat_cost_as_unknown", None))

    def test_zero_cost_high_work_events_returns_true(self):
        assert should_treat_cost_as_unknown(reported_cost=0.0, work_events=176217) is True

    def test_zero_cost_zero_work_events_returns_false(self):
        assert should_treat_cost_as_unknown(reported_cost=0.0, work_events=0) is False

    def test_positive_cost_returns_false(self):
        assert should_treat_cost_as_unknown(reported_cost=3.14, work_events=176217) is False

    def test_none_cost_high_work_events_returns_true(self):
        assert should_treat_cost_as_unknown(reported_cost=None, work_events=200) is True

    def test_none_cost_zero_work_events_returns_false(self):
        assert should_treat_cost_as_unknown(reported_cost=None, work_events=0) is False

    def test_just_above_threshold_returns_true(self):
        assert should_treat_cost_as_unknown(reported_cost=0.0, work_events=101) is True

    def test_at_threshold_returns_false(self):
        assert should_treat_cost_as_unknown(reported_cost=0.0, work_events=100) is False

    def test_below_threshold_returns_false(self):
        assert should_treat_cost_as_unknown(reported_cost=0.0, work_events=50) is False

    def test_returns_bool(self):
        result = should_treat_cost_as_unknown(reported_cost=0.0, work_events=200)
        assert isinstance(result, bool)

    def test_orchestrator_integration(self):
        mod = importlib.import_module("bob3.orchestrator")
        assert callable(getattr(mod, "should_treat_cost_as_unknown", None))


# ---------------------------------------------------------------------------
# enforce_zero_cost_policy: named AC entry point
# ---------------------------------------------------------------------------


class TestEnforceZeroCostPolicy:
    """enforce_zero_cost_policy: named AC2 entry point for the zero-cost enforcement rule."""

    def test_importable(self):
        mod = importlib.import_module("bob3.cost_enforcement")
        assert callable(getattr(mod, "enforce_zero_cost_policy", None))

    def test_telemetry_loss_path_applies_ceiling(self):
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=20.0,
            feature_id="9b2e1060-0000-0000-0000-000000000000",
        )
        assert result.telemetry_lost is True
        assert result.effective_cost == pytest.approx(20.0)

    def test_free_retry_path_zero_cost(self):
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=20.0,
            feature_id="spawn-crash",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(0.0)

    def test_normal_cost_returned_unchanged(self):
        result = enforce_zero_cost_policy(
            reported_cost=3.14,
            work_events=5000,
            per_feature_ceiling=20.0,
            feature_id="normal-feature",
        )
        assert result.telemetry_lost is False
        assert result.effective_cost == pytest.approx(3.14)

    def test_boundary_zero_input_returns_well_defined_result(self):
        """AC5 boundary: zero/empty inputs return a well-defined result rather than crashing."""
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-zero",
        )
        assert isinstance(result, CostValidationResult)
        assert isinstance(result.effective_cost, float)
        assert isinstance(result.telemetry_lost, bool)

    def test_none_cost_boundary_returns_well_defined_result(self):
        """AC5 boundary: None cost coerced to 0.0, does not crash."""
        result = enforce_zero_cost_policy(
            reported_cost=None,
            work_events=0,
            per_feature_ceiling=10.0,
            feature_id="boundary-none-cost",
        )
        assert isinstance(result, CostValidationResult)

    def test_invalid_negative_ceiling_raises_value_error(self):
        """AC6: raises ValueError for invalid (negative) per_feature_ceiling."""
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-1.0,
                feature_id="invalid-ceiling",
            )

    def test_invalid_zero_ceiling_raises_value_error(self):
        """AC6: raises ValueError for invalid (zero) per_feature_ceiling."""
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id="zero-ceiling",
            )

    def test_does_not_silently_succeed_on_bad_ceiling(self):
        """AC6: invalid input must raise, not return a silent success."""
        raised = False
        try:
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-5.0,
                feature_id="silent-fail-check",
            )
        except ValueError:
            raised = True
        assert raised, "enforce_zero_cost_policy must raise ValueError for invalid ceiling"

    def test_budget_not_disabled_on_zero_cost_high_events(self):
        """MUST NOT disable budget enforcement when work_events > threshold."""
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=176217,
            per_feature_ceiling=10.0,
            feature_id="no-disable",
        )
        assert result.effective_cost > 0.0

    def test_returns_cost_validation_result_type(self):
        result = enforce_zero_cost_policy(
            reported_cost=0.0,
            work_events=500,
            per_feature_ceiling=15.0,
            feature_id="type-check",
        )
        assert isinstance(result, CostValidationResult)

    def test_orchestrator_integration(self):
        mod = importlib.import_module("bob3.orchestrator")
        assert callable(getattr(mod, "enforce_zero_cost_policy", None))
