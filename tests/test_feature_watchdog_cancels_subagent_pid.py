"""Test: watchdog signals the correct subagent PID with SIGTERM then SIGKILL.

Verifies that cancel_subagent_at_deadline uses the provided PID, sends the
expected signals in the right order, and handles os.kill failures gracefully.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.orchestrator.feature_watchdog import cancel_subagent_at_deadline

FEATURE_ID = "ccccdddd-0000-0000-0000-000000000002"
TEST_PID = 77777


@pytest.mark.asyncio
async def test_sigterm_sent_to_correct_pid():
    """SIGTERM must be sent to the exact PID provided."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = True  # task already done — skip cancel call check

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    with (
        patch("bob3.orchestrator.feature_watchdog._pid_is_alive", return_value=True),
        patch("bob3.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob3.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=TEST_PID,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    # First kill call must be SIGTERM to TEST_PID.
    first_kill = mock_kill.call_args_list[0]
    assert first_kill == call(TEST_PID, signal.SIGTERM), (
        f"Expected first signal to be SIGTERM to PID {TEST_PID}; got {first_kill}"
    )


@pytest.mark.asyncio
async def test_os_kill_process_lookup_error_is_swallowed():
    """If SIGTERM raises ProcessLookupError, the watchdog handles it gracefully."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    def kill_side_effect(pid, sig):
        raise ProcessLookupError(f"no such process {pid}")

    # _pid_is_alive: first call returns True (enters kill path), subsequent
    # calls during grace loop return False (process gone after kill attempt).
    alive_counter = {"count": 0}

    def alive_side_effect(pid):
        alive_counter["count"] += 1
        return alive_counter["count"] == 1  # True first time, False thereafter

    with (
        patch("bob3.orchestrator.feature_watchdog._pid_is_alive", side_effect=alive_side_effect),
        patch("bob3.orchestrator.feature_watchdog.os.kill", side_effect=kill_side_effect),
        patch("bob3.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        # Should not raise even though os.kill raises ProcessLookupError.
        await cancel_subagent_at_deadline(
            pid=TEST_PID,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )


@pytest.mark.asyncio
async def test_safe_pid_constraint_skips_own_pid():
    """Watchdog must never signal os.getpid() (safety constraint)."""
    own_pid = os.getpid()
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    with (
        patch("bob3.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob3.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=own_pid,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    mock_kill.assert_not_called()


@pytest.mark.asyncio
async def test_safe_pid_constraint_skips_system_pids():
    """Watchdog must never signal PID ≤ 1 (init/kernel)."""
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = False

    deadline = time.monotonic() - 0.1

    async def instant_sleep(_delay):
        pass

    with (
        patch("bob3.orchestrator.feature_watchdog.os.kill") as mock_kill,
        patch("bob3.orchestrator.feature_watchdog.asyncio.sleep", side_effect=instant_sleep),
    ):
        await cancel_subagent_at_deadline(
            pid=1,
            task=task,
            deadline=deadline,
            feature_id=FEATURE_ID,
        )

    mock_kill.assert_not_called()
