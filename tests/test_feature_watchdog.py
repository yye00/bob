"""Tests for bob3.feature_watchdog public API.

Covers:
- FeatureWatchdog class: arms and cancels watchdog as a context manager.
- spawn_feature_watchdog: returns an asyncio.Task that fires at deadline.
- Integration: both are importable from bob3.feature_watchdog.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from unittest.mock import MagicMock, patch

import pytest

from bob3.feature_watchdog import (
    FeatureWatchdog,
    cancel_subagent_at_deadline,
    compute_deadline,
    spawn_feature_watchdog,
)

FEATURE_ID = "bb5d6c27-8431-4e27-9787-76117839af1a"
TEST_PID = 99991

# Patch target: the name as bound in bob3.feature_watchdog (the importer module)
_ARM_PATCH = "bob3.feature_watchdog.arm_feature_watchdog"


# ---------------------------------------------------------------------------
# Smoke-import tests
# ---------------------------------------------------------------------------


def test_feature_watchdog_class_is_importable():
    """FeatureWatchdog must be importable from bob3.feature_watchdog."""
    assert FeatureWatchdog is not None


def test_spawn_feature_watchdog_is_importable():
    """spawn_feature_watchdog must be importable from bob3.feature_watchdog."""
    assert callable(spawn_feature_watchdog)


# ---------------------------------------------------------------------------
# compute_deadline
# ---------------------------------------------------------------------------


def test_compute_deadline_returns_future_monotonic():
    """compute_deadline must return a value > time.monotonic()."""
    before = time.monotonic()
    dl = compute_deadline(10.0)
    after = time.monotonic()
    assert dl > before
    assert dl <= after + 10.0 + 0.1


def test_compute_deadline_raises_on_non_positive():
    """compute_deadline must raise ValueError for timeout_seconds <= 0."""
    with pytest.raises(ValueError):
        compute_deadline(0)
    with pytest.raises(ValueError):
        compute_deadline(-1)


# ---------------------------------------------------------------------------
# spawn_feature_watchdog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_feature_watchdog_returns_task():
    """spawn_feature_watchdog must return an asyncio.Task."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_task = MagicMock(spec=asyncio.Task)
        mock_arm.return_value = mock_task

        result = spawn_feature_watchdog(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=3600,
        )

    mock_arm.assert_called_once_with(
        pid=TEST_PID,
        task=task,
        feature_id=FEATURE_ID,
        timeout_seconds=3600,
    )
    assert result is mock_task


@pytest.mark.asyncio
async def test_spawn_feature_watchdog_passes_none_timeout():
    """spawn_feature_watchdog forwards None timeout to arm_feature_watchdog."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_task = MagicMock(spec=asyncio.Task)
        mock_arm.return_value = mock_task

        spawn_feature_watchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID)

    _, kwargs = mock_arm.call_args
    assert kwargs["timeout_seconds"] is None


# ---------------------------------------------------------------------------
# FeatureWatchdog context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_watchdog_arms_on_enter():
    """FeatureWatchdog.__aenter__ must call arm_feature_watchdog."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        fw = FeatureWatchdog(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=60,
        )
        async with fw:
            assert fw.watchdog_task is mock_wdog

    mock_arm.assert_called_once()


@pytest.mark.asyncio
async def test_feature_watchdog_cancels_on_exit_when_not_done():
    """FeatureWatchdog.__aexit__ must cancel the watchdog task if it is still running."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = False

        # Simulate awaiting the mock task: it raises CancelledError (normal path).
        async def _mock_await(*args, **kwargs):
            raise asyncio.CancelledError()

        mock_wdog.__await__ = MagicMock(return_value=iter([]))
        mock_arm.return_value = mock_wdog

        fw = FeatureWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID)
        async with fw:
            pass

    mock_wdog.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_feature_watchdog_does_not_cancel_already_done_task():
    """FeatureWatchdog must not call cancel() if the watchdog already completed."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        async with FeatureWatchdog(
            pid=TEST_PID, task=task, feature_id=FEATURE_ID
        ):
            pass

    mock_wdog.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_feature_watchdog_property_none_before_enter():
    """watchdog_task must be None before the context is entered."""
    task = asyncio.current_task()
    fw = FeatureWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID)
    assert fw.watchdog_task is None


@pytest.mark.asyncio
async def test_feature_watchdog_propagates_inner_exception():
    """Exceptions raised inside the context block must propagate."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        with pytest.raises(ValueError, match="boom"):
            async with FeatureWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID):
                raise ValueError("boom")


@pytest.mark.asyncio
async def test_feature_watchdog_passes_correct_args_to_arm():
    """FeatureWatchdog must pass pid, task, feature_id, timeout_seconds to arm."""
    task = asyncio.current_task()

    with patch(_ARM_PATCH) as mock_arm:
        mock_wdog = MagicMock(spec=asyncio.Task)
        mock_wdog.done.return_value = True
        mock_arm.return_value = mock_wdog

        async with FeatureWatchdog(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=1800,
        ):
            pass

    mock_arm.assert_called_once_with(
        pid=TEST_PID,
        task=task,
        feature_id=FEATURE_ID,
        timeout_seconds=1800,
    )


# ---------------------------------------------------------------------------
# cancel_subagent_at_deadline (re-exported from orchestrator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_subagent_at_deadline_no_op_when_already_exited():
    """When PID already exited, cancel_subagent_at_deadline is a no-op."""
    dispatcher_task = MagicMock(spec=asyncio.Task)
    dispatcher_task.done.return_value = False

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_d):
        pass

    with (
        patch("bob3.orchestrator.feature_watchdog._pid_is_alive", return_value=False),
        patch("bob3.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob3.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=TEST_PID,
            task=dispatcher_task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    mock_kill.assert_not_called()
    dispatcher_task.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_subagent_at_deadline_signals_alive_pid():
    """When PID is alive and deadline passed, SIGTERM then SIGKILL are sent."""
    dispatcher_task = MagicMock(spec=asyncio.Task)
    dispatcher_task.done.return_value = False

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_d):
        pass

    with (
        patch("bob3.orchestrator.feature_watchdog._pid_is_alive", return_value=True),
        patch("bob3.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob3.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
        patch(
            "bob3.orchestrator.feature_watchdog.time.monotonic",
            side_effect=[
                time.monotonic() - 0.2,
                time.monotonic() - 0.2,
                time.monotonic() + 100.0,
            ],
        ),
    ):
        await cancel_subagent_at_deadline(
            pid=TEST_PID,
            task=dispatcher_task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    sigterm_calls = [c for c in mock_kill.call_args_list if c.args[1] == signal.SIGTERM]
    sigkill_calls = [c for c in mock_kill.call_args_list if c.args[1] == signal.SIGKILL]
    assert sigterm_calls, "Expected SIGTERM"
    assert sigkill_calls, "Expected SIGKILL after grace period"
    dispatcher_task.cancel.assert_called_once()
