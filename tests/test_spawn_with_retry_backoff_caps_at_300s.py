"""F-R7-478: spawn_with_retry exponential backoff caps at 300 s."""

import asyncio
import pytest
from bob3.orchestrator.spawn_retry import spawn_with_retry


@pytest.mark.asyncio
async def test_backoff_never_exceeds_300s():
    """Verify that backoff values are always <= 300 s."""
    sleep_calls: list[float] = []

    async def no_sleep(s: float):
        sleep_calls.append(s)

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 15:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET: socket hang up",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    await spawn_with_retry(
        spawn_fn,
        feature_id="backoff-test",
        job_name="backoff_cap",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    assert len(sleep_calls) >= 14
    for s in sleep_calls:
        assert s <= 300.0, f"Backoff {s}s exceeds 300s cap"


@pytest.mark.asyncio
async def test_backoff_grows_exponentially_until_cap():
    """Verify the backoff sequence grows then plateaus at 300 s."""
    sleep_calls: list[float] = []

    async def no_sleep(s: float):
        sleep_calls.append(s)

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 12:
            return {
                "exit_code": 1,
                "stderr": "ETIMEDOUT",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    await spawn_with_retry(
        spawn_fn,
        feature_id="backoff-growth-test",
        job_name="backoff_growth",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    # Earlier sleeps should be smaller than later sleeps (growth phase).
    assert sleep_calls[0] < sleep_calls[1] < sleep_calls[2]
    # Later sleeps should all be 300 s (cap is hit at attempt index 9: 2^9=512 > 300).
    assert all(s == 300.0 for s in sleep_calls[9:])
