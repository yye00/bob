"""Boundary tests for infra-error transient classifier + spawn-layer recovery.

Empty / zero / minimum inputs must return a well-defined result rather than
raising (boundary case AC).
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.spawn_retry import classify_exit, spawn_with_retry


# ---------------------------------------------------------------------------
# classify_exit boundary cases
# ---------------------------------------------------------------------------


def test_classify_exit_none_exit_code_none_stderr():
    """None exit_code and None stderr must not raise."""
    result = classify_exit(exit_code=None, stderr=None)
    assert result in ("transient", "mid_work_crash", "real_failure")


def test_classify_exit_zero_work_events():
    """Zero work_events is boundary — must not raise."""
    result = classify_exit(exit_code=1, stderr="", work_events=0)
    assert result in ("transient", "mid_work_crash", "real_failure")


def test_classify_exit_empty_stderr():
    """Empty string stderr must not raise."""
    result = classify_exit(exit_code=1, stderr="")
    assert result in ("transient", "mid_work_crash", "real_failure")


def test_classify_exit_zero_duration_ms_no_work_events():
    """duration_ms=0 with no work_events must not raise."""
    result = classify_exit(exit_code=1, stderr="", duration_ms=0, work_events=0)
    assert result in ("transient", "mid_work_crash", "real_failure")


def test_classify_exit_zero_exit_code_no_stderr():
    """exit_code=0 is the minimal success boundary — always real_failure bucket."""
    result = classify_exit(exit_code=0, stderr="")
    assert result == "real_failure"


def test_classify_exit_minimum_work_events_one():
    """work_events=1 is the minimum non-zero value — must not raise."""
    result = classify_exit(exit_code=1, stderr="", work_events=1, duration_ms=1000)
    assert result in ("transient", "mid_work_crash", "real_failure")


def test_classify_exit_all_none_params():
    """All optional params as None must not raise."""
    result = classify_exit(exit_code=None, stderr=None, duration_ms=None, work_events=None)
    assert result in ("transient", "mid_work_crash", "real_failure")


@pytest.mark.asyncio
async def test_spawn_with_retry_immediate_success_boundary():
    """Boundary: spawn callable succeeds on first attempt — no retry loop entered."""

    async def spawn_fn():
        return {"exit_code": 0, "stderr": "", "duration_ms": 0, "work_events": 0, "cost_usd": 0.0}

    async def no_sleep(_s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="boundary-test",
        job_name="boundary",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_spawn_with_retry_zero_cost_boundary():
    """Boundary: spawn with zero cost must not trip any ceiling."""

    async def spawn_fn():
        return {"exit_code": 0, "stderr": "", "duration_ms": 1, "work_events": 0, "cost_usd": 0.0}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="zero-cost-boundary",
        job_name="zero_cost",
        sleep_fn=None,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
