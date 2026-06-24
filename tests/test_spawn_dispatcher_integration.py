"""Integration test: bob3.orchestrator.spawn_dispatcher routes all spawns through spawn_with_retry.

AC 20: integration: bob3.orchestrator.spawn_dispatcher
"""

from __future__ import annotations

import asyncio
import pytest

from bob3.orchestrator.spawn_dispatcher import dispatch_spawn


@pytest.mark.asyncio
async def test_dispatch_spawn_routes_through_retry_on_transient():
    """dispatch_spawn retries transient errors without calling on_real_failure."""
    call_count = 0

    async def flaky_spawn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return {"exit_code": 1, "stderr": "ECONNRESET: socket hang up", "duration_ms": 0, "work_events": 0, "cost_usd": 0.0}
        return {"exit_code": 0, "stderr": "", "duration_ms": 200, "work_events": 1, "cost_usd": 0.01}

    real_failure_calls: list = []

    result = await dispatch_spawn(
        flaky_spawn,
        feature_id="test-dispatch-transient",
        job_name="dispatch_transient_test",
        on_real_failure=lambda r: real_failure_calls.append(r),
        probe_fn=lambda: True,
        sleep_fn=lambda s: asyncio.sleep(0),
    )

    assert result["exit_code"] == 0
    assert call_count == 3
    assert len(real_failure_calls) == 0


@pytest.mark.asyncio
async def test_dispatch_spawn_returns_real_failure_result():
    """dispatch_spawn returns real_failure result and calls callback."""

    async def failing_spawn():
        return {"exit_code": 1, "stderr": "AssertionError: test failed", "duration_ms": 300, "work_events": 0, "cost_usd": 0.02}

    real_failure_calls: list = []

    result = await dispatch_spawn(
        failing_spawn,
        feature_id="test-dispatch-real-fail",
        job_name="dispatch_real_fail_test",
        on_real_failure=lambda r: real_failure_calls.append(r),
        probe_fn=lambda: True,
        sleep_fn=lambda s: asyncio.sleep(0),
    )

    assert result["exit_code"] == 1
    assert len(real_failure_calls) == 1


@pytest.mark.asyncio
async def test_dispatch_spawn_success_on_first_try():
    """dispatch_spawn returns immediately on success without retrying."""
    call_count = 0

    async def successful_spawn():
        nonlocal call_count
        call_count += 1
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 1, "cost_usd": 0.01}

    result = await dispatch_spawn(
        successful_spawn,
        feature_id="test-dispatch-success",
        job_name="dispatch_success_test",
        probe_fn=lambda: True,
        sleep_fn=lambda s: asyncio.sleep(0),
    )

    assert result["exit_code"] == 0
    assert call_count == 1


@pytest.mark.asyncio
async def test_dispatch_spawn_mid_work_crash_calls_callback():
    """dispatch_spawn calls on_mid_work_crash for mid-work crashes."""

    async def mid_crash_spawn():
        return {"exit_code": 1, "stderr": "fatal error in message reader", "duration_ms": 500, "work_events": 5, "cost_usd": 0.05}

    mid_crash_calls: list = []

    result = await dispatch_spawn(
        mid_crash_spawn,
        feature_id="test-dispatch-mid-crash",
        job_name="dispatch_mid_crash_test",
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
        probe_fn=lambda: True,
        sleep_fn=lambda s: asyncio.sleep(0),
    )

    assert result["exit_code"] == 1
    assert len(mid_crash_calls) == 1
