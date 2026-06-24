"""Tests for bob3.classify_exit and bob3.spawn_with_retry (infra-error classifier).

Verifies that classify_exit correctly identifies transient infrastructure errors,
mid-work crashes, and real failures; and that spawn_with_retry retries transient
errors without budget impact.
"""

from __future__ import annotations

import asyncio

import pytest

from bob3.orchestrator.spawn_retry import classify_exit, spawn_with_retry


# ---------------------------------------------------------------------------
# classify_exit — transient patterns
# ---------------------------------------------------------------------------


def test_classify_exit_http_429_is_transient():
    result = classify_exit(exit_code=1, stderr="HTTP 429 Too Many Requests")
    assert result == "transient"


def test_classify_exit_rate_limit_is_transient():
    result = classify_exit(exit_code=1, stderr="rate-limit exceeded, try again later")
    assert result == "transient"


def test_classify_exit_econnreset_is_transient():
    result = classify_exit(exit_code=1, stderr="Error: ECONNRESET: connection reset")
    assert result == "transient"


def test_classify_exit_etimedout_is_transient():
    result = classify_exit(exit_code=1, stderr="ETIMEDOUT connecting to api.anthropic.com")
    assert result == "transient"


def test_classify_exit_enoent_claude_is_transient():
    result = classify_exit(exit_code=1, stderr="ENOENT: no such file or directory, spawn claude")
    assert result == "transient"


# ---------------------------------------------------------------------------
# classify_exit — real failure
# ---------------------------------------------------------------------------


def test_classify_exit_syntax_error_is_real_failure():
    result = classify_exit(exit_code=1, stderr="SyntaxError: unexpected token")
    assert result == "real_failure"


def test_classify_exit_exit_zero_is_not_retried():
    # exit_code=0 is treated as real_failure bucket (caller interprets as success).
    result = classify_exit(exit_code=0, stderr=None)
    assert result == "real_failure"


def test_classify_exit_unknown_error_is_real_failure():
    result = classify_exit(exit_code=1, stderr="AssertionError: expected True")
    assert result == "real_failure"


# ---------------------------------------------------------------------------
# classify_exit — mid-work crash
# ---------------------------------------------------------------------------


def test_classify_exit_work_events_nonzero_is_mid_work_crash():
    result = classify_exit(exit_code=1, stderr="unknown fatal error", work_events=5, duration_ms=1000)
    assert result == "mid_work_crash"


def test_classify_exit_work_events_with_duration_zero_is_transient():
    # duration_ms=0 with work_events > 0 → JSONL race / SIGPIPE → transient
    result = classify_exit(exit_code=1, stderr="", work_events=3, duration_ms=0)
    assert result == "transient"


# ---------------------------------------------------------------------------
# classify_exit — type validation
# ---------------------------------------------------------------------------


def test_classify_exit_string_exit_code_raises_type_error():
    with pytest.raises(TypeError):
        classify_exit(exit_code="1", stderr="")  # type: ignore[arg-type]


def test_classify_exit_string_work_events_raises_type_error():
    with pytest.raises(TypeError):
        classify_exit(exit_code=1, stderr="", work_events="five")  # type: ignore[arg-type]


def test_classify_exit_string_duration_ms_raises_type_error():
    with pytest.raises(TypeError):
        classify_exit(exit_code=1, stderr="", duration_ms="fast")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# spawn_with_retry — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_returns_on_first_success():
    async def spawn_fn():
        return {"exit_code": 0, "stderr": "", "duration_ms": 500, "work_events": 0, "cost_usd": 0.01}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-success",
        job_name="test",
        sleep_fn=asyncio.sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# spawn_with_retry — transient retry without budget impact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_transient_errors():
    """Transient errors are retried unlimited times; no budget callback fires."""
    calls = []
    real_failure_calls = []
    mid_work_crash_calls = []

    async def spawn_fn():
        calls.append(len(calls))
        if len(calls) < 3:
            return {"exit_code": 1, "stderr": "HTTP 429", "duration_ms": 0, "work_events": 0, "cost_usd": 0.0}
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.01}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="transient-retry-test",
        job_name="transient",
        sleep_fn=lambda _: asyncio.sleep(0),
        probe_fn=lambda: True,
        on_real_failure=real_failure_calls.append,
        on_mid_work_crash=mid_work_crash_calls.append,
    )

    assert result["exit_code"] == 0
    assert len(calls) == 3
    # Budget callbacks must NOT fire on transient retries.
    assert len(real_failure_calls) == 0
    assert len(mid_work_crash_calls) == 0


@pytest.mark.asyncio
async def test_spawn_with_retry_real_failure_fires_callback():
    """real_failure classification invokes on_real_failure callback."""
    real_failure_calls = []

    async def spawn_fn():
        return {"exit_code": 1, "stderr": "SyntaxError: bad code", "duration_ms": 200, "work_events": 0, "cost_usd": 0.01}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="real-failure-test",
        job_name="real_fail",
        sleep_fn=lambda _: asyncio.sleep(0),
        probe_fn=lambda: True,
        on_real_failure=real_failure_calls.append,
    )

    assert result["exit_code"] == 1
    assert len(real_failure_calls) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_mid_work_crash_fires_callback():
    """mid_work_crash classification invokes on_mid_work_crash callback."""
    mid_work_crash_calls = []

    async def spawn_fn():
        return {"exit_code": 1, "stderr": "fatal error", "duration_ms": 1000, "work_events": 5, "cost_usd": 0.05}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="mid-work-crash-test",
        job_name="mid_crash",
        sleep_fn=lambda _: asyncio.sleep(0),
        probe_fn=lambda: True,
        on_mid_work_crash=mid_work_crash_calls.append,
    )

    assert result["exit_code"] == 1
    assert len(mid_work_crash_calls) == 1
