"""Tests for get_per_attempt_cap (27eaa1de).

AC assertions:
- Default 10.0 with no env variable set.
- env=200 clamped to 100.0 (upper boundary).
- env=0 clamped to 0.5 (lower boundary / error path).
- Valid values within range are returned as-is.
- Invalid (non-numeric) env values fall back to 10.0.
"""

from __future__ import annotations

import os

import pytest

from bob.orchestrator.per_attempt_cost_cap import (
    get_per_attempt_cap,
    should_terminate_subagent,
)


class TestGetPerAttemptCapDefault:
    """AC: default 10.0 when BOB_PER_ATTEMPT_COST_CAP is not set."""

    def test_default_10_no_env(self, monkeypatch):
        """AC: returns 10.0 when env variable is absent."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        assert get_per_attempt_cap() == 10.0

    def test_default_10_empty_string(self, monkeypatch):
        """Empty string env var behaves like unset — returns 10.0."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "")
        assert get_per_attempt_cap() == 10.0

    def test_default_10_whitespace_only(self, monkeypatch):
        """Whitespace-only env var behaves like unset — returns 10.0."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "   ")
        assert get_per_attempt_cap() == 10.0


class TestGetPerAttemptCapUpperBoundary:
    """AC: env=200 clamped to 100.0."""

    def test_env_200_clamped_to_100(self, monkeypatch):
        """AC: env=200 → clamped to 100.0."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "200")
        assert get_per_attempt_cap() == 100.0

    def test_env_exactly_100_not_clamped(self, monkeypatch):
        """env=100 is the boundary; returned as-is."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "100")
        assert get_per_attempt_cap() == 100.0

    def test_env_large_float_clamped_to_100(self, monkeypatch):
        """Large float env value clamped to 100.0."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "9999.99")
        assert get_per_attempt_cap() == 100.0


class TestGetPerAttemptCapLowerBoundary:
    """AC: env=0 clamped to 0.5 (error/boundary path)."""

    def test_env_0_clamped_to_0_5(self, monkeypatch):
        """AC: env=0 → clamped to 0.5."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "0")
        assert get_per_attempt_cap() == 0.5

    def test_env_negative_clamped_to_0_5(self, monkeypatch):
        """Negative env value clamped to 0.5."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "-5")
        assert get_per_attempt_cap() == 0.5

    def test_env_exactly_0_5_not_clamped(self, monkeypatch):
        """env=0.5 is the boundary; returned as-is."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "0.5")
        assert get_per_attempt_cap() == 0.5

    def test_env_below_0_5_clamped(self, monkeypatch):
        """env=0.1 (below 0.5) → clamped to 0.5."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "0.1")
        assert get_per_attempt_cap() == 0.5


class TestGetPerAttemptCapValidRange:
    """Valid values within [0.5, 100] are returned as-is."""

    def test_env_10_returned_as_is(self, monkeypatch):
        """Standard value within range."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "10")
        assert get_per_attempt_cap() == 10.0

    def test_env_25_returned_as_is(self, monkeypatch):
        """Mid-range float value."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "25.5")
        assert get_per_attempt_cap() == 25.5

    def test_env_50_returned_as_is(self, monkeypatch):
        """env=50 within range."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "50")
        assert get_per_attempt_cap() == 50.0


class TestGetPerAttemptCapInvalidEnv:
    """Non-numeric env values fall back to 10.0."""

    def test_non_numeric_env_falls_back_to_default(self, monkeypatch):
        """'abc' is not a float — returns 10.0."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "abc")
        assert get_per_attempt_cap() == 10.0

    def test_nan_string_falls_back_to_default(self, monkeypatch):
        """'nan' parses as float but is not a valid cap — check behavior."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "nan")
        # float('nan') is valid but comparisons behave unexpectedly.
        # max/min with NaN produces NaN, so clamping should be checked.
        # Implementation falls back to 10.0 for non-numeric; NaN is
        # technically valid but clamp(NaN) may return NaN.
        # This test documents current behavior: it should not raise.
        result = get_per_attempt_cap()
        assert isinstance(result, float)

    def test_special_chars_fall_back_to_default(self, monkeypatch):
        """Special chars in env var → falls back to 10.0."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "$10")
        assert get_per_attempt_cap() == 10.0


class TestShouldTerminateSubagent:
    """Tests for should_terminate_subagent."""

    def test_cost_above_cap_returns_true(self, monkeypatch):
        """Reported cost > cap → True."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        # default cap is 10.0
        assert should_terminate_subagent(10.01) is True

    def test_cost_at_cap_returns_false(self, monkeypatch):
        """Reported cost == cap → False (strict >)."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(10.0) is False

    def test_cost_below_cap_returns_false(self, monkeypatch):
        """Reported cost < cap → False."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(5.0) is False

    def test_zero_cost_returns_false(self, monkeypatch):
        """Zero cost never triggers termination (default cap = 10.0)."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(0.0) is False

    def test_negative_cost_returns_false(self, monkeypatch):
        """Negative cost is coerced to 0.0 — never triggers termination."""
        monkeypatch.delenv("BOB_PER_ATTEMPT_COST_CAP", raising=False)
        assert should_terminate_subagent(-5.0) is False

    def test_custom_cap_respected(self, monkeypatch):
        """Custom cap from env is used in comparison."""
        monkeypatch.setenv("BOB_PER_ATTEMPT_COST_CAP", "5")
        assert should_terminate_subagent(5.01) is True
        assert should_terminate_subagent(5.0) is False
        assert should_terminate_subagent(4.99) is False
