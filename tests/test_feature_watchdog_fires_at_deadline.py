"""Test: watchdog fires cancel_subagent_at_deadline after the deadline passes.

Verifies that cancel_subagent_at_deadline actually invokes task.cancel() when
the deadline is reached and the target PID is still alive.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from unittest.mock import MagicMock, patch

import pytest

from bob.orchestrator.feature_watchdog import (
    cancel_subagent_at_deadline,
    compute_deadline,
)

FEATURE_ID = "aaaabbbb-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_watchdog_cancels_task_at_deadline_with_alive_pid():
    """When the deadline passes and the PID is alive, the task must be cancelled."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    # Deadline is in the past (already expired).
    deadline = time.monotonic() - 0.1

    with (
        patch("bob.orchestrator.feature_watchdog._pid_is_alive", return_value=True),
        patch("bob.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("asyncio.sleep", new_callable=lambda: lambda *_: asyncio.coroutine(lambda *_: None)()),
    ):
        # Re-patch asyncio.sleep so it doesn't actually sleep.
        async def instant_sleep(_delay):
            pass

        with patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep):
            await cancel_subagent_at_deadline(
                pid=12345,
                task=task,
                deadline=deadline,
                feature_id=FEATURE_ID,
            )

    task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_watchdog_sends_sigterm_then_sigkill_when_pid_survives():
    """When PID survives SIGTERM grace period, SIGKILL is sent."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    # Already-expired deadline.
    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    # Simulate: PID is always alive so the grace loop times out → SIGKILL fires.
    # After SIGKILL, _pid_is_alive is not checked again by the current impl
    # (SIGKILL path just sends and falls through to task.cancel).
    with (
        patch("bob.orchestrator.feature_watchdog._pid_is_alive", return_value=True),
        patch("bob.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
        # Make grace period expire immediately so the while loop exits.
        patch(
            "bob.orchestrator.feature_watchdog.time.monotonic",
            side_effect=[
                # compute remaining before sleep: returns -0.1 (deadline already past)
                time.monotonic() - 0.2,
                # grace_end = monotonic() + 5.0
                time.monotonic() - 0.2,
                # while monotonic() < grace_end: first check → already past grace_end
                time.monotonic() + 100.0,
            ],
        ),
    ):
        await cancel_subagent_at_deadline(
            pid=12345,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    # SIGTERM should have been sent.
    sigterm_calls = [
        c for c in mock_kill.call_args_list if c.args[1] == signal.SIGTERM
    ]
    assert sigterm_calls, "Expected SIGTERM to be sent to the subagent PID"

    # SIGKILL should have been sent (process didn't exit during grace period).
    sigkill_calls = [
        c for c in mock_kill.call_args_list if c.args[1] == signal.SIGKILL
    ]
    assert sigkill_calls, "Expected SIGKILL to be sent after SIGTERM grace expired"


@pytest.mark.asyncio
async def test_watchdog_cancelled_before_deadline_raises_cancelled_error():
    """When the watchdog task itself is cancelled before deadline, CancelledError propagates."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    # Far-future deadline so sleep actually runs.
    deadline = time.monotonic() + 9999.0

    async def cancel_during_sleep(_delay):
        raise asyncio.CancelledError()

    with patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=cancel_during_sleep):
        with pytest.raises(asyncio.CancelledError):
            await cancel_subagent_at_deadline(
                pid=12345,
                task=task,
                deadline=deadline,
                feature_id=FEATURE_ID,
            )

    # Task should NOT have been cancelled — the watchdog itself was cancelled.
    task.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_watchdog_does_not_cancel_already_done_task():
    """When the awaited task is already done, watchdog skips cancellation."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = True  # already finished

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    with (
        patch("bob.orchestrator.feature_watchdog._pid_is_alive", return_value=True),
        patch("bob.orchestrator.feature_watchdog.os.kill"),
        patch("bob.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=12345,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    task.cancel.assert_not_called()
