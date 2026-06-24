"""F-R7-478: transient retries NEVER increment any budget counter."""

import asyncio
import pytest
from bob.orchestrator.spawn_retry import spawn_with_retry


@pytest.mark.asyncio
async def test_transient_retries_never_call_on_real_failure():
    """on_real_failure callback is not called during transient retries."""
    real_failure_calls = []
    mid_crash_calls = []

    async def no_sleep(s):
        pass

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    await spawn_with_retry(
        spawn_fn,
        feature_id="budget-test",
        job_name="no_budget",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_calls.append(r),
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
    )

    assert len(real_failure_calls) == 0, "on_real_failure was called during transient retries"
    assert len(mid_crash_calls) == 0, "on_mid_work_crash was called during transient retries"


@pytest.mark.asyncio
async def test_mid_work_crash_calls_exactly_once():
    """on_mid_work_crash is called exactly once for a mid-work crash."""
    mid_crash_calls = []

    async def no_sleep(s):
        pass

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "Fatal error in message reader",
            "duration_ms": 15000,
            "work_events": 3,
            "cost_usd": 0.05,
        }

    await spawn_with_retry(
        spawn_fn,
        feature_id="mid-crash-test",
        job_name="mid_crash",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
    )

    assert len(mid_crash_calls) == 1, f"Expected 1 mid-work-crash call, got {len(mid_crash_calls)}"


@pytest.mark.asyncio
async def test_real_failure_calls_exactly_once():
    """on_real_failure is called exactly once for a real failure."""
    real_failure_calls = []

    async def no_sleep(s):
        pass

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "SyntaxError: invalid syntax",
            "duration_ms": 5000,
            "work_events": 0,
            "cost_usd": 0.02,
        }

    await spawn_with_retry(
        spawn_fn,
        feature_id="real-fail-test",
        job_name="real_fail",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_calls.append(r),
    )

    assert len(real_failure_calls) == 1, f"Expected 1 real_failure call, got {len(real_failure_calls)}"
