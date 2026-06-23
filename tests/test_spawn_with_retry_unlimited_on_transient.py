"""F-R7-478: spawn_with_retry retries unlimited times on transient exits."""

import asyncio
import pytest
from bob3.orchestrator.spawn_retry import spawn_with_retry


@pytest.mark.asyncio
async def test_retries_until_success():
    """spawn_with_retry retries a transient failure and eventually succeeds."""
    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 5:
            return {
                "exit_code": 1,
                "stderr": "Error: ECONNRESET: socket hang up",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 1000, "work_events": 0, "cost_usd": 0.1}

    async def no_sleep(s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-feat-1",
        job_name="test_job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    assert result["exit_code"] == 0
    assert call_count == 5


@pytest.mark.asyncio
async def test_retries_11_transient_then_success():
    """Simulates 10 transient failures followed by success (AC demonstrator pattern)."""
    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 10:
            return {
                "exit_code": 1,
                "stderr": "HTTP 429 Too Many Requests",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 500, "work_events": 0, "cost_usd": 0.05}

    async def no_sleep(s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-feat-2",
        job_name="test_unlimited",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
    assert call_count == 11


@pytest.mark.asyncio
async def test_real_failure_returns_immediately():
    """A real failure is returned after a single attempt without retrying."""
    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        return {
            "exit_code": 1,
            "stderr": "SyntaxError: invalid syntax",
            "duration_ms": 5000,
            "work_events": 0,
            "cost_usd": 0.01,
        }

    async def no_sleep(s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-feat-3",
        job_name="test_real",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 1
    assert call_count == 1
