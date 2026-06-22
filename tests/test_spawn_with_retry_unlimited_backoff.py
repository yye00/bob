"""Tests for spawn_layer.spawn_with_retry unlimited transient retry + backoff cap.

Verifies:
- Transient exits are retried unlimited times without budget impact.
- Exponential backoff is applied on each retry.
- Backoff is capped at 300 s (config: BACKOFF_CAP_SECONDS).
- Budget callbacks (on_real_failure, on_mid_work_crash) are NOT called for transient.
- on_real_failure / on_mid_work_crash ARE called for their respective outcomes.
- spawn_with_retry returns successfully on eventual non-transient exit.
"""

from __future__ import annotations

import asyncio

import pytest

from spawn_layer import classify_exit, spawn_with_retry


# ---------------------------------------------------------------------------
# Helper: build a spawn callable that fails N times then succeeds
# ---------------------------------------------------------------------------


def _make_transient_then_success(transient_count: int):
    """Return an async spawn callable that yields ECONNRESET N times then exit_code=0."""
    calls = {"n": 0}

    async def spawn_fn():
        calls["n"] += 1
        if calls["n"] <= transient_count:
            return {
                "exit_code": 1,
                "stderr": "connect ECONNRESET network blip",
                "duration_ms": 100,
                "work_events": 0,
                "cost_usd": 0.01,
            }
        return {
            "exit_code": 0,
            "stderr": "",
            "duration_ms": 5000,
            "work_events": 10,
            "cost_usd": 0.10,
        }

    return spawn_fn, calls


# ---------------------------------------------------------------------------
# Core retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_retried_until_success():
    """spawn_with_retry must retry transient exits and return on success."""
    slept: list[float] = []

    async def _sleep(s: float):
        slept.append(s)

    spawn_fn, calls = _make_transient_then_success(3)

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-unlimited-retry",
        job_name="test_unlimited",
        sleep_fn=_sleep,
        probe_fn=lambda: True,
    )

    assert result["exit_code"] == 0
    assert calls["n"] == 4  # 3 transient + 1 success
    assert len(slept) == 3  # one sleep per transient retry


@pytest.mark.asyncio
async def test_transient_does_not_call_real_failure_callback():
    """on_real_failure must NOT be called during transient retries."""
    real_failure_called = []

    async def _sleep(_s: float):
        pass

    spawn_fn, _ = _make_transient_then_success(2)

    await spawn_with_retry(
        spawn_fn,
        feature_id="no-budget-charge",
        job_name="no_budget",
        sleep_fn=_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_called.append(r),
    )

    assert len(real_failure_called) == 0


@pytest.mark.asyncio
async def test_transient_does_not_call_mid_work_crash_callback():
    """on_mid_work_crash must NOT be called during transient retries."""
    mid_crash_called = []

    async def _sleep(_s: float):
        pass

    spawn_fn, _ = _make_transient_then_success(1)

    await spawn_with_retry(
        spawn_fn,
        feature_id="no-mid-crash",
        job_name="no_mid",
        sleep_fn=_sleep,
        probe_fn=lambda: True,
        on_mid_work_crash=lambda r: mid_crash_called.append(r),
    )

    assert len(mid_crash_called) == 0


# ---------------------------------------------------------------------------
# Backoff cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backoff_cap_not_exceeded():
    """Backoff values must never exceed 300 s regardless of attempt count."""
    slept: list[float] = []

    async def _sleep(s: float):
        slept.append(s)

    spawn_fn, _ = _make_transient_then_success(10)

    await spawn_with_retry(
        spawn_fn,
        feature_id="backoff-cap-test",
        job_name="cap_test",
        sleep_fn=_sleep,
        probe_fn=lambda: True,
    )

    assert all(s <= 300.0 for s in slept), f"Backoff exceeded 300 s: {slept}"


@pytest.mark.asyncio
async def test_backoff_increases_between_attempts():
    """Exponential backoff must increase across successive attempts (up to cap)."""
    slept: list[float] = []

    async def _sleep(s: float):
        slept.append(s)

    spawn_fn, _ = _make_transient_then_success(4)

    await spawn_with_retry(
        spawn_fn,
        feature_id="backoff-increase",
        job_name="backoff_inc",
        sleep_fn=_sleep,
        probe_fn=lambda: True,
    )

    # First backoff <= second backoff (exponential growth until cap)
    assert len(slept) >= 2
    assert slept[1] >= slept[0]


# ---------------------------------------------------------------------------
# Real failure and mid-work crash callbacks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_failure_callback_invoked():
    """on_real_failure must be called when classification is real_failure."""
    called = []

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "AssertionError: wrong answer",
            "duration_ms": 3000,
            "work_events": 0,
            "cost_usd": 0.05,
        }

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="real-fail-cb",
        job_name="real_fail",
        sleep_fn=None,
        probe_fn=lambda: True,
        on_real_failure=lambda r: called.append(r),
    )

    assert result["exit_code"] == 1
    assert len(called) == 1


@pytest.mark.asyncio
async def test_mid_work_crash_callback_invoked():
    """on_mid_work_crash must be called when classification is mid_work_crash."""
    called = []

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "fatal shutdown",
            "duration_ms": 8000,
            "work_events": 5,
            "cost_usd": 0.20,
        }

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="mid-crash-cb",
        job_name="mid_crash",
        sleep_fn=None,
        probe_fn=lambda: True,
        on_mid_work_crash=lambda r: called.append(r),
    )

    assert result["exit_code"] == 1
    assert len(called) == 1


# ---------------------------------------------------------------------------
# Immediate success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_retry_on_immediate_success():
    """spawn_with_retry must not retry when the first attempt returns exit_code=0."""
    calls = {"n": 0}

    async def spawn_fn():
        calls["n"] += 1
        return {
            "exit_code": 0,
            "stderr": "",
            "duration_ms": 1000,
            "work_events": 5,
            "cost_usd": 0.10,
        }

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="immediate-ok",
        job_name="immediate",
        sleep_fn=None,
        probe_fn=lambda: True,
    )

    assert result["exit_code"] == 0
    assert calls["n"] == 1
