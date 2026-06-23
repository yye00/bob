"""Test: arm_feature_watchdog reads BOB3_FEATURE_TIMEOUT_SECONDS from env.

Verifies that _resolve_timeout_seconds (called by arm_feature_watchdog when
timeout_seconds is None) honours the BOB3_FEATURE_TIMEOUT_SECONDS env var and
falls back to 3600 on missing, invalid, or non-positive values.
"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.orchestrator.feature_watchdog import (
    _DEFAULT_FEATURE_TIMEOUT_SECONDS,
    _resolve_timeout_seconds,
    arm_feature_watchdog,
)

FEATURE_ID = "11112222-0000-0000-0000-000000000004"


# ---------------------------------------------------------------------------
# _resolve_timeout_seconds unit tests
# ---------------------------------------------------------------------------

def test_env_not_set_returns_default(monkeypatch):
    """When BOB3_FEATURE_TIMEOUT_SECONDS is not set, default (3600) is returned."""
    monkeypatch.delenv("BOB3_FEATURE_TIMEOUT_SECONDS", raising=False)
    result = _resolve_timeout_seconds()
    assert result == float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)


def test_env_set_to_valid_value(monkeypatch):
    """When BOB3_FEATURE_TIMEOUT_SECONDS=120, 120.0 is returned."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "120")
    result = _resolve_timeout_seconds()
    assert result == 120.0


def test_env_set_to_float(monkeypatch):
    """Fractional values like '45.5' are accepted."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "45.5")
    result = _resolve_timeout_seconds()
    assert result == 45.5


def test_env_invalid_string_returns_default(monkeypatch):
    """Non-numeric BOB3_FEATURE_TIMEOUT_SECONDS falls back to the default."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "not_a_number")
    result = _resolve_timeout_seconds()
    assert result == float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)


def test_env_zero_returns_default(monkeypatch):
    """Zero BOB3_FEATURE_TIMEOUT_SECONDS falls back to the default."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0")
    result = _resolve_timeout_seconds()
    assert result == float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)


def test_env_negative_returns_default(monkeypatch):
    """Negative BOB3_FEATURE_TIMEOUT_SECONDS falls back to the default."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "-300")
    result = _resolve_timeout_seconds()
    assert result == float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# arm_feature_watchdog integration test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_arm_watchdog_uses_env_timeout(monkeypatch):
    """arm_feature_watchdog with timeout_seconds=None reads BOB3_FEATURE_TIMEOUT_SECONDS."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "300")

    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    # We test that arm_feature_watchdog creates a task and immediately cancel it.
    loop = asyncio.get_event_loop()

    # Patch cancel_subagent_at_deadline to record the deadline it received.
    recorded = {}

    async def fake_cancel(pid, task_, deadline, feature_id):
        recorded["deadline"] = deadline
        # Immediately return (simulating watchdog cancelled).

    with patch(
        "bob3.orchestrator.feature_watchdog.cancel_subagent_at_deadline",
        side_effect=fake_cancel,
    ):
        before = time.monotonic()
        watchdog = arm_feature_watchdog(
            pid=12345,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=None,  # should read env
        )
        # Let the event loop tick so the task body starts.
        await asyncio.sleep(0)
        watchdog.cancel()
        try:
            await watchdog
        except (asyncio.CancelledError, Exception):
            pass

    # The deadline should be ~300 seconds from when we called arm_feature_watchdog.
    assert "deadline" in recorded, "cancel_subagent_at_deadline was not called"
    assert recorded["deadline"] >= before + 300
    assert recorded["deadline"] <= before + 300 + 2.0


@pytest.mark.asyncio
async def test_arm_watchdog_explicit_timeout_overrides_env(monkeypatch):
    """When timeout_seconds is given explicitly, the env var is ignored."""
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "9999")

    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    recorded = {}

    async def fake_cancel(pid, task_, deadline, feature_id):
        recorded["deadline"] = deadline

    with patch(
        "bob3.orchestrator.feature_watchdog.cancel_subagent_at_deadline",
        side_effect=fake_cancel,
    ):
        before = time.monotonic()
        watchdog = arm_feature_watchdog(
            pid=12345,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=60,  # explicit — should NOT read env
        )
        await asyncio.sleep(0)
        watchdog.cancel()
        try:
            await watchdog
        except (asyncio.CancelledError, Exception):
            pass

    assert "deadline" in recorded
    # Should be ~60s from start, NOT 9999s.
    assert recorded["deadline"] >= before + 60
    assert recorded["deadline"] <= before + 60 + 2.0
