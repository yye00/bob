"""Test: watchdog is a no-op when the subagent PID already exited.

Verifies that cancel_subagent_at_deadline does NOT send signals and does NOT
cancel the task when _pid_is_alive returns False (process already gone).
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from bob.orchestrator.feature_watchdog import cancel_subagent_at_deadline

FEATURE_ID = "eeeeffff-0000-0000-0000-000000000003"
TEST_PID = 99999


@pytest.mark.asyncio
async def test_no_signal_when_pid_already_dead():
    """When the process is already dead at deadline, no signals are sent."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    # Expired deadline.
    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    with (
        patch("bob.orchestrator.feature_watchdog._pid_is_alive", return_value=False),
        patch("bob.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=TEST_PID,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    mock_kill.assert_not_called()
    task.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_no_task_cancel_when_pid_already_dead():
    """Task.cancel() must not be called when the process already exited."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    with (
        patch("bob.orchestrator.feature_watchdog._pid_is_alive", return_value=False),
        patch("bob.orchestrator.feature_watchdog.os.kill"),
        patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=TEST_PID,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    task.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_watchdog_task_cancels_cleanly_when_subagent_exits_normally():
    """When caller cancels the watchdog (subagent done), CancelledError propagates cleanly."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    # Far-future deadline — sleep will be interrupted by cancellation.
    deadline = time.monotonic() + 9999.0

    async def sleep_then_cancel(_delay):
        raise asyncio.CancelledError()

    with patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=sleep_then_cancel):
        with pytest.raises(asyncio.CancelledError):
            await cancel_subagent_at_deadline(
                pid=TEST_PID,
                task=task,
                deadline=deadline,
                feature_id=FEATURE_ID,
            )

    # PID check and kill should never have been reached.
    task.cancel.assert_not_called()
