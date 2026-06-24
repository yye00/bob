"""Tests for bob.cost_control (bb0c4b7a).

AC: pytest: tests/test_cost_control.py
AC: Function defined: bob.cost_control.enforce_per_attempt_cost_cap
AC: Function defined: bob.cost_control.terminate_subagent_on_cap
AC: integration: bob.orchestrator

Covers:
- Module imports and function existence
- enforce_per_attempt_cost_cap returns False when cost is within cap
- enforce_per_attempt_cost_cap returns True and calls termination when cap exceeded
- terminate_subagent_on_cap delegates to the lower-level implementation
- Invalid typed inputs raise (TypeError or ValueError)
- Integration: cost_control functions are importable alongside orchestrator modules
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import bob.cost_control as cost_control_mod
from bob.cost_control import (
    enforce_per_attempt_cost_cap,
    terminate_subagent_on_cap,
)

_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_SAFE_PID = 99999


class TestModuleExists:
    """AC: File exists: src/bob/cost_control.py"""

    def test_module_importable(self):
        """bob.cost_control must be importable without error."""
        import bob.cost_control  # noqa: F401

    def test_enforce_per_attempt_cost_cap_defined(self):
        """bob.cost_control.enforce_per_attempt_cost_cap must be a callable."""
        assert callable(enforce_per_attempt_cost_cap)

    def test_terminate_subagent_on_cap_defined(self):
        """bob.cost_control.terminate_subagent_on_cap must be a callable."""
        assert callable(terminate_subagent_on_cap)


class TestEnforcePerAttemptCostCapHappyPath:
    """enforce_per_attempt_cost_cap returns False when cost is within cap."""

    def test_zero_cost_returns_false(self, monkeypatch):
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        result = enforce_per_attempt_cost_cap(
            feature_id=_FEATURE_ID,
            pid=_SAFE_PID,
            reported_cost=0.0,
        )
        assert result is False

    def test_cost_below_default_cap_returns_false(self, monkeypatch):
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        result = enforce_per_attempt_cost_cap(
            feature_id=_FEATURE_ID,
            pid=_SAFE_PID,
            reported_cost=5.0,
        )
        assert result is False

    def test_cost_exactly_at_default_cap_returns_false(self, monkeypatch):
        """Cost exactly at 10.0 is not strictly > cap; returns False."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        result = enforce_per_attempt_cost_cap(
            feature_id=_FEATURE_ID,
            pid=_SAFE_PID,
            reported_cost=10.0,
        )
        assert result is False

    def test_negative_cost_returns_false(self, monkeypatch):
        """Negative cost (bad telemetry) must return False, not trigger termination."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        result = enforce_per_attempt_cost_cap(
            feature_id=_FEATURE_ID,
            pid=_SAFE_PID,
            reported_cost=-5.0,
        )
        assert result is False


class TestEnforcePerAttemptCostCapTriggersTermination:
    """enforce_per_attempt_cost_cap returns True and calls termination when cap exceeded."""

    def test_cost_above_default_cap_returns_true(self, monkeypatch):
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob.cost_control.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=10.01,
            )

        assert result is True
        mock_term.assert_called_once_with(
            feature_id=_FEATURE_ID,
            pid=_SAFE_PID,
            reported_cost=10.01,
        )

    def test_cost_well_above_cap_triggers_termination(self, monkeypatch):
        """A $38 runaway cost (as observed) triggers termination."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob.cost_control.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=38.25,
            )

        assert result is True
        mock_term.assert_called_once()

    def test_custom_cap_via_env_var(self, monkeypatch):
        """Custom cap via BOB_PER_ATTEMPT_COST_CAP is respected."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "5.0")

        with patch("bob.cost_control.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=5.5,
            )

        assert result is True
        mock_term.assert_called_once()

    def test_custom_cap_under_threshold_not_triggered(self, monkeypatch):
        """Custom cap of $5; cost of $4.99 must not trigger termination."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "5.0")

        with patch("bob.cost_control.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=4.99,
            )

        assert result is False
        mock_term.assert_not_called()


class TestTerminateSubagentOnCap:
    """terminate_subagent_on_cap delegates to the lower-level implementation."""

    def test_delegates_to_lower_level(self, monkeypatch):
        """terminate_subagent_on_cap must call terminate_subagent_on_cost_cap."""
        with patch("bob.cost_control.terminate_subagent_on_cost_cap") as mock_term:
            terminate_subagent_on_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=15.0,
            )

        mock_term.assert_called_once_with(
            feature_id=_FEATURE_ID,
            pid=_SAFE_PID,
            reported_cost=15.0,
        )

    def test_returns_none(self, monkeypatch):
        """terminate_subagent_on_cap must return None."""
        with patch("bob.cost_control.terminate_subagent_on_cost_cap"):
            result = terminate_subagent_on_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=15.0,
            )
        assert result is None


class TestInvalidInputRaises:
    """Invalid typed inputs must raise (TypeError or ValueError), not silently succeed."""

    def test_none_reported_cost_raises(self, monkeypatch):
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=None,  # type: ignore[arg-type]
            )

    def test_string_reported_cost_raises(self, monkeypatch):
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost="not_a_number",  # type: ignore[arg-type]
            )

    def test_dict_reported_cost_raises(self, monkeypatch):
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost={},  # type: ignore[arg-type]
            )


class TestOrchestratorIntegration:
    """AC: integration: bob.orchestrator — cost_control works alongside orchestrator modules."""

    def test_orchestrator_per_attempt_cost_cap_importable_alongside(self):
        """Both modules must be importable together without conflict."""
        from bob.cost_control import enforce_per_attempt_cost_cap as ctrl_enforce
        from bob.orchestrator.per_attempt_cost_cap import (
            get_per_attempt_cap,
            should_terminate_subagent,
            terminate_subagent_on_cost_cap,
        )
        assert callable(ctrl_enforce)
        assert callable(get_per_attempt_cap)
        assert callable(should_terminate_subagent)
        assert callable(terminate_subagent_on_cost_cap)

    def test_cost_control_and_cost_cap_consistent_default(self, monkeypatch):
        """cost_control and cost_cap modules must use the same default cap (10.0)."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        from bob.orchestrator.per_attempt_cost_cap import get_per_attempt_cap
        cap = get_per_attempt_cap()
        assert cap == 10.0

    def test_env_override_propagates_to_cost_control(self, monkeypatch):
        """BOB_PER_ATTEMPT_COST_CAP env var override is visible from cost_control."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "7.5")
        from bob.orchestrator.per_attempt_cost_cap import get_per_attempt_cap
        cap = get_per_attempt_cap()
        assert cap == 7.5

        with patch("bob.cost_control.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=8.0,
            )
        assert result is True
        mock_term.assert_called_once()
