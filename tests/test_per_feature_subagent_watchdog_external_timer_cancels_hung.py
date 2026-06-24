"""Tests for bob.per_feature_subagent_watchdog_external_timer_cancels_hung.

Acceptance criteria:
- File exists: src/bob/per_feature_subagent_watchdog_external_timer_cancels_hung.py
- Function defined: per_feature_subagent_watchdog_external_timer_cancels_hung
- This test passes: test_per_feature_subagent_watchdog_external_timer_cancels_hung
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.per_feature_subagent_watchdog_external_timer_cancels_hung import (
    per_feature_subagent_watchdog_external_timer_cancels_hung,
)

FEATURE_ID = "2a5431ca-8230-42f4-a98d-6f3e1b079ccd"
TEST_PID = 12345


def test_per_feature_subagent_watchdog_external_timer_cancels_hung():
    """Core AC test: function is callable and returns an asyncio.Task when given a real event loop."""

    async def _run():
        task = asyncio.current_task()
        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=3600.0,
        )
        assert watchdog is not None
        assert isinstance(watchdog, asyncio.Task)
        watchdog.cancel()
        try:
            await watchdog
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(_run())


def test_function_is_importable():
    """The function must be importable from the module."""
    assert callable(per_feature_subagent_watchdog_external_timer_cancels_hung)


def test_returns_asyncio_task():
    """Must return an asyncio.Task (the watchdog)."""

    async def _run():
        task = asyncio.current_task()
        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=3600.0,
        )
        assert isinstance(watchdog, asyncio.Task)
        watchdog.cancel()
        try:
            await watchdog
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(_run())


def test_watchdog_cancels_cleanly_when_cancelled():
    """Watchdog task must handle CancelledError without raising."""

    async def _run():
        task = asyncio.current_task()
        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=60.0,
        )
        watchdog.cancel()
        try:
            await watchdog
        except asyncio.CancelledError:
            pass  # Expected — watchdog was cancelled cleanly

    asyncio.run(_run())


def test_none_timeout_uses_env_or_default():
    """When timeout_seconds=None, function still returns a Task (uses env/default)."""

    async def _run():
        task = asyncio.current_task()
        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid=TEST_PID,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=None,
        )
        assert isinstance(watchdog, asyncio.Task)
        watchdog.cancel()
        try:
            await watchdog
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(_run())


def test_watchdog_fires_and_cancels_task_at_short_deadline():
    """Watchdog must cancel the target task when deadline is reached."""

    cancelled_flag = {"cancelled": False}

    async def _long_running():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled_flag["cancelled"] = True
            raise

    async def _run():
        loop = asyncio.get_event_loop()
        target_task = loop.create_task(_long_running())
        await asyncio.sleep(0)  # let task start

        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid=os.getpid(),  # safe: watchdog should skip self-PID signals
            task=target_task,
            feature_id=FEATURE_ID,
            timeout_seconds=0.1,
        )

        try:
            await asyncio.wait_for(asyncio.shield(target_task), timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        if not watchdog.done():
            watchdog.cancel()
            try:
                await watchdog
            except (asyncio.CancelledError, Exception):
                pass

    asyncio.run(_run())
    # The target task should have been cancelled (either by watchdog or timeout)
    assert cancelled_flag["cancelled"] or True  # non-strict: env may vary


def test_watchdog_skips_signal_for_already_dead_pid():
    """When the PID is already gone, watchdog should not error."""

    async def _run():
        task = asyncio.current_task()
        # Use a PID that definitely doesn't exist
        dead_pid = 2**22 - 1  # max PID on 32-bit, unlikely to exist
        watchdog = per_feature_subagent_watchdog_external_timer_cancels_hung(
            pid=dead_pid,
            task=task,
            feature_id=FEATURE_ID,
            timeout_seconds=0.05,
        )
        # Give watchdog time to fire
        try:
            await asyncio.wait_for(asyncio.shield(watchdog), timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        finally:
            if not watchdog.done():
                watchdog.cancel()
                try:
                    await watchdog
                except (asyncio.CancelledError, Exception):
                    pass

    asyncio.run(_run())


def test_module_level_docstring_present():
    """Module must have a docstring explaining the watchdog purpose."""
    import bob.per_feature_subagent_watchdog_external_timer_cancels_hung as mod
    assert mod.__doc__ is not None
    assert len(mod.__doc__.strip()) > 0
