"""Tests for bob3.per_attempt_cost_cap (feature 29bde5f2).

Verifies that enforce_per_attempt_cost_cap is importable from
bob3.per_attempt_cost_cap and behaves correctly.
"""

from __future__ import annotations

from unittest.mock import patch, call
import pytest

from bob3.per_attempt_cost_cap import enforce_per_attempt_cost_cap
from bob3.orchestrator.per_attempt_cost_cap import (
    get_per_attempt_cap,
    should_terminate_subagent,
)

_FEATURE_ID = "29bde5f2-cd6d-4994-bc50-e448a8c3fcbd"
_SAFE_PID = 99999


class TestEnforcePerAttemptCostCapImport:
    """enforce_per_attempt_cost_cap is importable from bob3.per_attempt_cost_cap."""

    def test_function_is_callable(self):
        assert callable(enforce_per_attempt_cost_cap)

    def test_function_name(self):
        assert enforce_per_attempt_cost_cap.__name__ == "enforce_per_attempt_cost_cap"


class TestEnforcePerAttemptCostCapBelowCap:
    """Cost below cap returns False without terminating subagent."""

    def test_cost_below_cap_returns_false(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=5.0,
            )
        assert result is False
        mock_term.assert_not_called()

    def test_cost_exactly_at_cap_returns_false(self, monkeypatch):
        """Cap check is strict >; exactly at cap should not terminate."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=10.0,
            )
        assert result is False
        mock_term.assert_not_called()

    def test_zero_cost_returns_false(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=0.0,
            )
        assert result is False
        mock_term.assert_not_called()


class TestEnforcePerAttemptCostCapAboveCap:
    """Cost above cap returns True and initiates termination."""

    def test_cost_above_cap_returns_true(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=10.01,
            )
        assert result is True
        mock_term.assert_called_once()

    def test_runaway_cost_returns_true(self, monkeypatch):
        """Simulate the $38.25 runaway burn scenario."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=38.25,
            )
        assert result is True
        mock_term.assert_called_once()

    def test_custom_cap_env_respected(self, monkeypatch):
        """Custom cap from BOB3_PER_ATTEMPT_COST_CAP is enforced."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "5")
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=5.01,
            )
        assert result is True
        mock_term.assert_called_once()

    def test_custom_cap_below_threshold_no_kill(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "5")
        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_term:
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=4.99,
            )
        assert result is False
        mock_term.assert_not_called()


class TestDefaultCap:
    """Default cap is $10.0 when no env var is set."""

    def test_default_cap_is_10(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        cap = get_per_attempt_cap()
        assert cap == 10.0

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "20")
        cap = get_per_attempt_cap()
        assert cap == 20.0

    def test_env_clamped_below_minimum(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "0")
        cap = get_per_attempt_cap()
        assert cap == 0.5

    def test_env_clamped_above_maximum(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "999")
        cap = get_per_attempt_cap()
        assert cap == 100.0


class TestOrchestratorIntegration:
    """Verify the module is importable and wired into bob3.orchestrator."""

    def test_import_from_bob3_per_attempt_cost_cap(self):
        """Primary AC: module importable at bob3.per_attempt_cost_cap."""
        from bob3.per_attempt_cost_cap import enforce_per_attempt_cost_cap as fn
        assert callable(fn)

    def test_orchestrator_has_per_attempt_cost_cap(self):
        """bob3.orchestrator.per_attempt_cost_cap module is importable."""
        from bob3.orchestrator.per_attempt_cost_cap import (
            get_per_attempt_cap,
            should_terminate_subagent,
            terminate_subagent_on_cost_cap,
        )
        assert callable(get_per_attempt_cap)
        assert callable(should_terminate_subagent)
        assert callable(terminate_subagent_on_cost_cap)
