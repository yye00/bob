"""Tests for infra-error transient classifier + unlimited spawn-layer recovery.

AC: pytest: tests/test_infra_error.py
AC: Function defined: src.infra_error.classify_exit
AC: Function defined: src.infra_error.spawn_with_retry
AC: integration: research_agent
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import src.infra_error as infra_error
from src.infra_error import classify_exit, spawn_with_retry


# ---------------------------------------------------------------------------
# Importability checks (AC: Function defined: src.infra_error.classify_exit / spawn_with_retry)
# ---------------------------------------------------------------------------


def test_classify_exit_is_importable_from_src_infra_error():
    """classify_exit must be importable from src.infra_error."""
    assert callable(classify_exit)


def test_spawn_with_retry_is_importable_from_src_infra_error():
    """spawn_with_retry must be importable from src.infra_error."""
    assert callable(spawn_with_retry)


# ---------------------------------------------------------------------------
# classify_exit — transient pattern coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr",
    [
        "HTTP 429 Too Many Requests",
        "rate limit exceeded",
        "RateLimit: too many requests",
        "ECONNRESET on socket",
        "ETIMEDOUT connecting to api",
        "spawn ENOENT claude",
        "No such file or directory: claude",
        "shared API key and is being deprecated",
    ],
)
def test_classify_exit_transient_patterns(stderr: str):
    """Well-known infra-error patterns must classify as transient."""
    result = classify_exit(exit_code=1, stderr=stderr)
    assert result == "transient", f"Expected 'transient' for stderr={stderr!r}, got {result!r}"


def test_classify_exit_real_failure_generic():
    """Generic implementation failure with no infra markers → real_failure."""
    result = classify_exit(exit_code=1, stderr="AssertionError: expected 42 got 0")
    assert result == "real_failure"


def test_classify_exit_mid_work_crash():
    """Sub-agent that wrote work_events and then died → mid_work_crash."""
    result = classify_exit(exit_code=1, stderr="unexpected shutdown", work_events=3, duration_ms=5000)
    assert result == "mid_work_crash"


def test_classify_exit_jsonl_race_reclassified_as_transient():
    """work_events > 0 with duration_ms == 0 → JSONL race → transient."""
    result = classify_exit(exit_code=1, stderr="unknown error", work_events=2, duration_ms=0)
    assert result == "transient"


def test_classify_exit_success_returns_real_failure_bucket():
    """exit_code == 0 is success; caller treats it as success not a failure."""
    result = classify_exit(exit_code=0, stderr="")
    assert result == "real_failure"


# ---------------------------------------------------------------------------
# spawn_with_retry — core retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_succeeds_immediately():
    """A spawn that succeeds on the first attempt returns without retrying."""
    calls: list[int] = []

    async def spawn_fn() -> dict[str, Any]:
        calls.append(1)
        return {"exit_code": 0, "stderr": "", "duration_ms": 10, "work_events": 0, "cost_usd": 0.01}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="feat-001",
        job_name="test_immediate",
        sleep_fn=lambda _s: asyncio.sleep(0),
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_transient_then_succeeds():
    """Transient failures must be retried; budget callbacks NOT called for transient."""
    attempts: list[int] = []
    budget_charges: list[dict] = []

    async def spawn_fn() -> dict[str, Any]:
        attempt_num = len(attempts) + 1
        attempts.append(attempt_num)
        if attempt_num < 3:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.05}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="feat-002",
        job_name="test_retry",
        sleep_fn=lambda _s: asyncio.sleep(0),
        probe_fn=lambda: True,
        on_real_failure=lambda r: budget_charges.append({"type": "real", **r}),
        on_mid_work_crash=lambda r: budget_charges.append({"type": "mid", **r}),
    )
    assert result["exit_code"] == 0
    assert len(attempts) == 3
    # Transient retries must NOT invoke budget callbacks
    assert budget_charges == [], f"Budget callbacks must not fire for transient retries, got: {budget_charges}"


@pytest.mark.asyncio
async def test_spawn_with_retry_real_failure_invokes_callback():
    """Real failures must invoke on_real_failure exactly once."""
    real_failures: list[dict] = []

    async def spawn_fn() -> dict[str, Any]:
        return {"exit_code": 1, "stderr": "assertion error", "duration_ms": 500, "work_events": 0, "cost_usd": 0.02}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="feat-003",
        job_name="test_real_fail",
        sleep_fn=lambda _s: asyncio.sleep(0),
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failures.append(r),
    )
    assert result["exit_code"] == 1
    assert len(real_failures) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_mid_work_crash_invokes_callback():
    """Mid-work crashes must invoke on_mid_work_crash exactly once."""
    mid_crashes: list[dict] = []

    async def spawn_fn() -> dict[str, Any]:
        return {
            "exit_code": 1,
            "stderr": "unexpected shutdown",
            "duration_ms": 3000,
            "work_events": 5,
            "cost_usd": 0.10,
        }

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="feat-004",
        job_name="test_mid_crash",
        sleep_fn=lambda _s: asyncio.sleep(0),
        probe_fn=lambda: True,
        on_mid_work_crash=lambda r: mid_crashes.append(r),
    )
    assert result["exit_code"] == 1
    assert len(mid_crashes) == 1


# ---------------------------------------------------------------------------
# Integration: research_agent uses spawn_with_retry
# ---------------------------------------------------------------------------


def test_research_agent_exposes_classify_exit():
    """research_agent must expose classify_exit from infra_error integration."""
    import src.research_agent as research_agent

    assert hasattr(research_agent, "classify_exit"), (
        "research_agent must re-export classify_exit for the infra_error integration AC"
    )
    assert callable(research_agent.classify_exit)


def test_research_agent_exposes_spawn_with_retry():
    """research_agent must expose spawn_with_retry from infra_error integration."""
    import src.research_agent as research_agent

    assert hasattr(research_agent, "spawn_with_retry"), (
        "research_agent must re-export spawn_with_retry for the infra_error integration AC"
    )
    assert callable(research_agent.spawn_with_retry)


def test_research_agent_classify_exit_works():
    """research_agent.classify_exit must classify transient errors correctly."""
    import src.research_agent as research_agent

    result = research_agent.classify_exit(exit_code=1, stderr="HTTP 429 rate limit")
    assert result == "transient"
