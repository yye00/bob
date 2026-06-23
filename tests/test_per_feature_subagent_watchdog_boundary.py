"""Boundary-case tests for bob3.feature_watchdog (per-feature subagent watchdog).

AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from bob3.orchestrator.feature_watchdog import compute_deadline, arm_feature_watchdog
from bob3.feature_watchdog import FeatureWatchdog, spawn_feature_watchdog

FEATURE_ID = "110b0899-09c3-4eab-b4f0-b29a6b0a764d"
TEST_PID = 99999

_ARM_PATCH = "bob3.feature_watchdog.arm_feature_watchdog"


def test_compute_deadline_minimum_positive_returns_value():
    """compute_deadline with a very small positive timeout must return a float > now."""
    before = time.monotonic()
    dl = compute_deadline(0.001)
    assert isinstance(dl, float)
    assert dl > before


def test_compute_deadline_large_value_returns_float():
    """compute_deadline with a very large timeout must return a float without raising."""
    dl = compute_deadline(86400 * 365)
    assert isinstance(dl, float)
    assert dl > time.monotonic()


@pytest.mark.asyncio
async def test_spawn_feature_watchdog_with_minimum_timeout_returns_task():
    """spawn_feature_watchdog with timeout_seconds=1 must return a non-None task."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_task = MagicMock(spec=asyncio.Task)
        mock_arm.return_value = mock_task

        result = spawn_feature_watchdog(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=1,
        )

    assert result is not None


@pytest.mark.asyncio
async def test_feature_watchdog_with_very_short_timeout_does_not_raise():
    """FeatureWatchdog context manager with 1-second timeout must not raise on entry/exit."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        async with FeatureWatchdog(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=1,
        ):
            pass


@pytest.mark.asyncio
async def test_feature_watchdog_none_timeout_uses_default():
    """FeatureWatchdog with timeout_seconds=None must not raise (uses env/default)."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        async with FeatureWatchdog(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=None,
        ):
            pass

    _, kwargs = mock_arm.call_args
    assert kwargs["timeout_seconds"] is None


@pytest.mark.asyncio
async def test_spawn_feature_watchdog_none_timeout_forwards_none():
    """spawn_feature_watchdog with no timeout arg passes None to arm."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_task = MagicMock(spec=asyncio.Task)
        mock_arm.return_value = mock_task

        spawn_feature_watchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID)

    _, kwargs = mock_arm.call_args
    assert kwargs["timeout_seconds"] is None


@pytest.mark.asyncio
async def test_feature_watchdog_empty_string_feature_id_does_not_raise():
    """FeatureWatchdog with an empty feature_id string must not raise on init."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        async with FeatureWatchdog(
            pid=TEST_PID,
            task=task,
            feature_id="",
            timeout_seconds=60,
        ):
            pass
