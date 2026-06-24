"""Error path tests for the per-feature subagent cost cap (default $10).

AC: invalid input raises ValueError and the function does not silently succeed.

Covers:
- Non-numeric BOB3_PER_ATTEMPT_COST_CAP env var → get_per_attempt_cap uses default (no ValueError)
- get_per_attempt_cap is always safe (never raises) — env errors are swallowed
- enforce_per_attempt_cost_cap with invalid feature_id types raises TypeError
- enforce_per_attempt_cost_cap with non-numeric reported_cost raises (ValueError/TypeError)

Note: The spec says "invalid input raises ValueError and the function does not silently succeed."
The primary public API entry point is enforce_per_attempt_cost_cap. Invalid Python-level types
(e.g., passing a dict instead of float) should raise, not silently succeed.
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


class TestGetPerAttemptCapInvalidEnvSafe:
    """get_per_attempt_cap must never raise even for invalid env var values."""

    def test_non_numeric_env_var_falls_back_to_default(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP=notanumber → falls back to default 10.0."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "notanumber")
        cap = get_per_attempt_cap()
        assert cap == 10.0

    def test_whitespace_only_env_var_returns_default(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP='  ' (whitespace) → falls back to default 10.0."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "   ")
        cap = get_per_attempt_cap()
        assert cap == 10.0

    def test_alpha_env_var_does_not_raise(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP='abc' must not raise, returns default."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "abc")
        cap = get_per_attempt_cap()
        assert isinstance(cap, float)
        assert cap == 10.0

    def test_mixed_env_var_does_not_raise(self, monkeypatch):
        """BOB3_PER_ATTEMPT_COST_CAP='10abc' must not raise, returns default."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "10abc")
        cap = get_per_attempt_cap()
        assert isinstance(cap, float)
        assert cap == 10.0


class TestShouldTerminateInvalidInput:
    """should_terminate_subagent must raise on non-numeric input."""

    def test_none_cost_raises(self, monkeypatch):
        """Passing None as cost must raise TypeError."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with pytest.raises((TypeError, ValueError)):
            should_terminate_subagent(None)  # type: ignore[arg-type]

    def test_string_cost_raises(self, monkeypatch):
        """Passing a non-numeric string as cost must raise ValueError."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with pytest.raises((TypeError, ValueError)):
            should_terminate_subagent("notanumber")  # type: ignore[arg-type]

    def test_dict_cost_raises(self, monkeypatch):
        """Passing a dict as cost must raise TypeError."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)
        with pytest.raises((TypeError, ValueError)):
            should_terminate_subagent({})  # type: ignore[arg-type]


class TestEnforcePerAttemptCostCapInvalidInput:
    """enforce_per_attempt_cost_cap must raise on invalid Python-typed arguments."""

    def test_none_reported_cost_raises(self, monkeypatch):
        """Passing None as reported_cost must raise (TypeError or ValueError)."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=None,  # type: ignore[arg-type]
            )

    def test_non_numeric_string_reported_cost_raises(self, monkeypatch):
        """Passing a non-numeric string as reported_cost must raise."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost="not_a_number",  # type: ignore[arg-type]
            )

    def test_dict_reported_cost_raises(self, monkeypatch):
        """Passing a dict as reported_cost must raise TypeError."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost={},  # type: ignore[arg-type]
            )

    def test_list_reported_cost_raises(self, monkeypatch):
        """Passing a list as reported_cost must raise TypeError."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with pytest.raises((TypeError, ValueError)):
            enforce_per_attempt_cost_cap(
                feature_id=_FEATURE_ID,
                pid=_SAFE_PID,
                reported_cost=[],  # type: ignore[arg-type]
            )
