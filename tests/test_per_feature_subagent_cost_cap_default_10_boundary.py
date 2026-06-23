"""Boundary cases for the per-feature subagent cost cap (default $10).

AC: empty, zero, or minimum input returns a well-defined result rather than raising.

Covers:
- Zero cost input → returns False (no termination), no exception
- Negative cost (bad telemetry) → returns False (no termination), no exception
- Cost exactly at minimum cap (0.5 after clamping) → behaves correctly
- Cost exactly at default cap (10.0) → returns False (not strictly >)
- Empty env var → uses default cap, no exception
- Non-numeric env var → uses default cap, no exception
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bob3.cost_cap import enforce_per_attempt_cost_cap
from bob3.orchestrator.per_attempt_cost_cap import (
    get_per_attempt_cap,
    should_terminate_subagent,
)

_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_SAFE_PID = 99999


class TestBoundaryCasesNeverRaise:
    """Boundary: zero, negative, and minimum values return a defined result."""

    def test_zero_cost_returns_false_no_exception(self, monkeypatch):
        """Zero cost input must return False and must not raise."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap"):
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=0.0,
            )

        assert result is False

    def test_negative_cost_returns_false_no_exception(self, monkeypatch):
        """Negative cost (bad telemetry) must return False and must not raise."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap"):
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=-100.0,
            )

        assert result is False

    def test_cost_exactly_at_default_cap_returns_false(self, monkeypatch):
        """Cost exactly at the default cap (10.0) is not strictly > cap; returns False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap"):
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=10.0,
            )

        assert result is False

    def test_cost_at_min_cap_boundary_no_exception(self, monkeypatch):
        """Cost equal to the minimum clamped cap (0.5) returns False, no exception."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "0.5")

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap"):
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=0.5,
            )

        assert result is False

    def test_cost_at_max_cap_boundary_no_exception(self, monkeypatch):
        """Cost equal to the maximum clamped cap (100) returns False, no exception."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "100")

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap"):
            result = enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=100.0,
            )

        assert result is False


class TestBoundaryCasesGetPerAttemptCap:
    """Boundary: get_per_attempt_cap handles edge env var values without raising."""

    def test_empty_env_var_returns_default(self, monkeypatch):
        """Empty BOB3_PER_ATTEMPT_COST_CAP returns default 10.0 cap."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "")
        cap = get_per_attempt_cap()
        assert cap == 10.0

    def test_zero_env_var_clamped_to_minimum(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP=0 is clamped to 0.5."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "0")
        cap = get_per_attempt_cap()
        assert cap == 0.5

    def test_very_large_env_var_clamped_to_maximum(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP=9999 is clamped to 100."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "9999")
        cap = get_per_attempt_cap()
        assert cap == 100.0

    def test_negative_env_var_clamped_to_minimum(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP=-5 is clamped to 0.5."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "-5")
        cap = get_per_attempt_cap()
        assert cap == 0.5

    def test_unset_env_var_returns_default(self, monkeypatch):
        """Unset BOB3_PER_ATTEMPT_COST_CAP returns default 10.0 cap."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        cap = get_per_attempt_cap()
        assert cap == 10.0


class TestBoundaryCasesShouldTerminate:
    """Boundary: should_terminate_subagent handles edge float values correctly."""

    def test_zero_cost_returns_false(self, monkeypatch):
        """should_terminate_subagent(0.0) must return False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(0.0) is False

    def test_negative_cost_returns_false(self, monkeypatch):
        """should_terminate_subagent(-0.01) must return False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(-0.01) is False

    def test_cost_at_cap_returns_false(self, monkeypatch):
        """should_terminate_subagent(10.0) must return False (strict >)."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(10.0) is False

    def test_cost_just_above_cap_returns_true(self, monkeypatch):
        """should_terminate_subagent(10.001) must return True."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(10.001) is True
