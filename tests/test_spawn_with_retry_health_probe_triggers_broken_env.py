"""F-R7-478: Health probe — 3 consecutive failures → BROKEN_ENV mode."""

import asyncio
import pytest
from bob.orchestrator.spawn_retry import spawn_with_retry


@pytest.mark.asyncio
async def test_broken_env_mode_after_3_probe_failures():
    """After 3 consecutive probe failures, broken_env backoff is used."""
    sleep_calls: list[float] = []
    probe_calls: list[bool] = []

    async def no_sleep(s: float):
        sleep_calls.append(s)

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 4:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    probe_return = [False, False, False, True, True]
    probe_idx = 0

    def probe_fn():
        nonlocal probe_idx
        result = probe_return[probe_idx] if probe_idx < len(probe_return) else True
        probe_calls.append(result)
        probe_idx += 1
        return result

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="broken-env-test",
        job_name="broken_env",
        sleep_fn=no_sleep,
        probe_fn=probe_fn,
    )

    assert result["exit_code"] == 0
    # After 3 consecutive failures the broken-env backoff (600s) should appear.
    assert any(s == 600.0 for s in sleep_calls), f"Expected 600s broken_env backoff in {sleep_calls}"


@pytest.mark.asyncio
async def test_env_recovery_resets_broken_env():
    """After broken env is detected, a successful probe resets the mode."""
    sleep_calls: list[float] = []

    async def no_sleep(s: float):
        sleep_calls.append(s)

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 6:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    # First 3 probes fail (broken env), then all succeed (recovery).
    probe_responses = [False, False, False, True, True, True, True]
    probe_idx = 0

    def probe_fn():
        nonlocal probe_idx
        r = probe_responses[probe_idx] if probe_idx < len(probe_responses) else True
        probe_idx += 1
        return r

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="env-recover-test",
        job_name="env_recover",
        sleep_fn=no_sleep,
        probe_fn=probe_fn,
    )

    assert result["exit_code"] == 0
    # After recovery, normal (non-600s) backoffs should appear again.
    normal_backoffs = [s for s in sleep_calls if s != 600.0]
    assert len(normal_backoffs) > 0, "Expected at least one normal backoff after recovery"
