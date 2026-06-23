"""Tests for bob3.subagent_watchdog — SubagentWatchdog and spawn_watchdog_task."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from bob3.subagent_watchdog import SubagentWatchdog, spawn_watchdog_task

FEATURE_ID = "9089a21d-be23-4d92-ba13-f1825f388af7"
TEST_PID = 99999

_ARM_PATCH = "bob3.subagent_watchdog.arm_feature_watchdog"


# ---------------------------------------------------------------------------
# Module-level symbol checks
# ---------------------------------------------------------------------------

def test_subagent_watchdog_class_exists():
    """SubagentWatchdog must be importable from bob3.subagent_watchdog."""
    assert SubagentWatchdog is not None


def test_spawn_watchdog_task_function_exists():
    """spawn_watchdog_task must be importable from bob3.subagent_watchdog."""
    assert callable(spawn_watchdog_task)


# ---------------------------------------------------------------------------
# spawn_watchdog_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spawn_watchdog_task_returns_task():
    """spawn_watchdog_task must return the asyncio.Task from arm_feature_watchdog."""
    task = asyncio.current_task()
    mock_task = MagicMock(spec=asyncio.Task)

    with patch(_ARM_PATCH, return_value=mock_task) as mock_arm:
        result = spawn_watchdog_task(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=60,
        )

    assert result is mock_task
    mock_arm.assert_called_once_with(
        pid=TEST_PID,
        task=task,
        feature_id=FEATURE_ID,
        timeout_seconds=60,
    )


@pytest.mark.asyncio
async def test_spawn_watchdog_task_none_timeout_forwards_none():
    """spawn_watchdog_task with no timeout passes timeout_seconds=None to arm."""
    task = asyncio.current_task()
    mock_task = MagicMock(spec=asyncio.Task)

    with patch(_ARM_PATCH, return_value=mock_task) as mock_arm:
        spawn_watchdog_task(pid=TEST_PID, task=task, feature_id=FEATURE_ID)

    _, kwargs = mock_arm.call_args
    assert kwargs["timeout_seconds"] is None


@pytest.mark.asyncio
async def test_spawn_watchdog_task_passes_feature_id():
    """spawn_watchdog_task must forward the feature_id to arm_feature_watchdog."""
    task = asyncio.current_task()
    mock_task = MagicMock(spec=asyncio.Task)

    with patch(_ARM_PATCH, return_value=mock_task) as mock_arm:
        spawn_watchdog_task(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=120)

    _, kwargs = mock_arm.call_args
    assert kwargs["feature_id"] == FEATURE_ID


@pytest.mark.asyncio
async def test_spawn_watchdog_task_passes_pid():
    """spawn_watchdog_task must forward the pid to arm_feature_watchdog."""
    task = asyncio.current_task()
    mock_task = MagicMock(spec=asyncio.Task)

    with patch(_ARM_PATCH, return_value=mock_task) as mock_arm:
        spawn_watchdog_task(pid=12345, task=task, feature_id=FEATURE_ID, timeout_seconds=120)

    _, kwargs = mock_arm.call_args
    assert kwargs["pid"] == 12345


# ---------------------------------------------------------------------------
# SubagentWatchdog context manager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subagent_watchdog_arms_on_entry():
    """SubagentWatchdog.__aenter__ must call arm_feature_watchdog."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = True

    with patch(_ARM_PATCH, return_value=mock_wdog) as mock_arm:
        async with SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60):
            pass

    mock_arm.assert_called_once()


@pytest.mark.asyncio
async def test_subagent_watchdog_cancels_on_normal_exit():
    """SubagentWatchdog must cancel the watchdog task when the block exits normally."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = False

    with patch(_ARM_PATCH, return_value=mock_wdog):
        async with SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60):
            pass

    mock_wdog.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_subagent_watchdog_skips_cancel_when_task_done():
    """SubagentWatchdog must not call cancel() when the watchdog task is already done."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = True

    with patch(_ARM_PATCH, return_value=mock_wdog):
        async with SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60):
            pass

    mock_wdog.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_subagent_watchdog_task_property_before_entry_is_none():
    """watchdog_task property must be None before __aenter__ is called."""
    task = asyncio.current_task()
    wdog = SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60)
    assert wdog.watchdog_task is None


@pytest.mark.asyncio
async def test_subagent_watchdog_task_property_set_after_entry():
    """watchdog_task property must be set after __aenter__."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = True

    with patch(_ARM_PATCH, return_value=mock_wdog):
        wdog = SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60)
        async with wdog:
            assert wdog.watchdog_task is mock_wdog


@pytest.mark.asyncio
async def test_subagent_watchdog_none_timeout_forwards_none():
    """SubagentWatchdog with timeout_seconds=None must pass None to arm."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = True

    with patch(_ARM_PATCH, return_value=mock_wdog) as mock_arm:
        async with SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=None):
            pass

    _, kwargs = mock_arm.call_args
    assert kwargs["timeout_seconds"] is None


@pytest.mark.asyncio
async def test_subagent_watchdog_propagates_exception():
    """SubagentWatchdog must propagate exceptions raised inside the block."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = True

    with patch(_ARM_PATCH, return_value=mock_wdog):
        with pytest.raises(RuntimeError, match="test error"):
            async with SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60):
                raise RuntimeError("test error")


@pytest.mark.asyncio
async def test_subagent_watchdog_cancels_on_exception():
    """SubagentWatchdog must still cancel the watchdog task when an exception is raised."""
    task = asyncio.current_task()
    mock_wdog = MagicMock(spec=asyncio.Task)
    mock_wdog.done.return_value = False

    with patch(_ARM_PATCH, return_value=mock_wdog):
        with pytest.raises(RuntimeError):
            async with SubagentWatchdog(pid=TEST_PID, task=task, feature_id=FEATURE_ID, timeout_seconds=60):
                raise RuntimeError("inner error")

    mock_wdog.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# Integration with run_loop
# ---------------------------------------------------------------------------

def test_run_loop_exports_create_subagent_watchdog():
    """bob3.run_loop must export create_subagent_watchdog."""
    from bob3 import run_loop
    assert hasattr(run_loop, "create_subagent_watchdog")
    assert callable(run_loop.create_subagent_watchdog)


def test_subagent_watchdog_module_all_exports():
    """bob3.subagent_watchdog.__all__ must include SubagentWatchdog and spawn_watchdog_task."""
    from bob3 import subagent_watchdog
    assert "SubagentWatchdog" in subagent_watchdog.__all__
    assert "spawn_watchdog_task" in subagent_watchdog.__all__
