"""Tests for infra_error.classify_exit and infra_error.spawn_with_retry.

Verifies that the top-level infra_error module exposes both functions and that
they behave correctly for all classification buckets and retry scenarios.

ACs covered:
- Function defined: infra_error.classify_exit
- Function defined: infra_error.spawn_with_retry
- pytest: tests/test_infra_error_classifier.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import infra_error


# ---------------------------------------------------------------------------
# AC verification: both functions must be importable and callable
# ---------------------------------------------------------------------------


def test_infra_error_has_classify_exit():
    assert callable(infra_error.classify_exit)


def test_infra_error_has_spawn_with_retry():
    assert callable(infra_error.spawn_with_retry)


# ---------------------------------------------------------------------------
# classify_exit — transient bucket (infra errors)
# ---------------------------------------------------------------------------


def test_classify_exit_http_429_is_transient():
    result = infra_error.classify_exit(exit_code=1, stderr="HTTP 429 Too Many Requests")
    assert result == "transient"


def test_classify_exit_rate_limit_is_transient():
    result = infra_error.classify_exit(exit_code=1, stderr="rate-limit exceeded please slow down")
    assert result == "transient"


def test_classify_exit_econnreset_is_transient():
    result = infra_error.classify_exit(exit_code=1, stderr="Error: ECONNRESET: socket hang up")
    assert result == "transient"


def test_classify_exit_etimedout_is_transient():
    result = infra_error.classify_exit(exit_code=1, stderr="ETIMEDOUT connecting to api.anthropic.com")
    assert result == "transient"


def test_classify_exit_enoent_claude_is_transient():
    result = infra_error.classify_exit(exit_code=1, stderr="spawn ENOENT: no such file: claude")
    assert result == "transient"


def test_classify_exit_deprecated_api_key_is_transient():
    result = infra_error.classify_exit(
        exit_code=1,
        stderr="shared API key and is being deprecated",
    )
    assert result == "transient"


# ---------------------------------------------------------------------------
# classify_exit — mid_work_crash bucket
# ---------------------------------------------------------------------------


def test_classify_exit_work_events_no_transient_is_mid_work_crash():
    result = infra_error.classify_exit(
        exit_code=1,
        stderr="unknown error",
        work_events=5,
        duration_ms=2000,
    )
    assert result == "mid_work_crash"


def test_classify_exit_message_reader_crash_is_mid_work_crash():
    result = infra_error.classify_exit(
        exit_code=1,
        stderr="fatal error in message reader",
    )
    assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# classify_exit — real_failure bucket
# ---------------------------------------------------------------------------


def test_classify_exit_success_exit_code_is_real_failure():
    result = infra_error.classify_exit(exit_code=0, stderr=None)
    assert result == "real_failure"


def test_classify_exit_syntax_error_is_real_failure():
    result = infra_error.classify_exit(exit_code=1, stderr="SyntaxError: unexpected EOF")
    assert result == "real_failure"


def test_classify_exit_no_work_no_transient_is_real_failure():
    result = infra_error.classify_exit(exit_code=1, stderr="implementation error: bad output")
    assert result == "real_failure"


# ---------------------------------------------------------------------------
# classify_exit — JSONL race reclassification
# ---------------------------------------------------------------------------


def test_classify_exit_work_events_duration_zero_is_transient():
    """work_events > 0 AND duration_ms == 0 → JSONL race → reclassified as transient."""
    result = infra_error.classify_exit(
        exit_code=1,
        stderr="",
        work_events=3,
        duration_ms=0,
    )
    assert result == "transient"


# ---------------------------------------------------------------------------
# spawn_with_retry — basic retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_success_first_attempt():
    async def spawn_fn() -> dict[str, Any]:
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.01}

    result = await infra_error.spawn_with_retry(
        spawn_fn,
        feature_id="ic-test-feat",
        job_name="ic-test",
        sleep_fn=asyncio.sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_transient_does_not_call_real_failure():
    """Transient retries must NOT invoke on_real_failure."""
    calls: list[str] = []

    async def spawn_fn() -> dict[str, Any]:
        calls.append("spawn")
        if len(calls) < 3:
            return {
                "exit_code": 1,
                "stderr": "HTTP 429 Too Many Requests",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.01}

    real_failure_calls: list[Any] = []

    async def instant_sleep(_: float) -> None:
        pass

    result = await infra_error.spawn_with_retry(
        spawn_fn,
        feature_id="ic-retry-feat",
        job_name="ic-retry",
        sleep_fn=instant_sleep,
        probe_fn=lambda: True,
        on_real_failure=real_failure_calls.append,
    )
    assert result["exit_code"] == 0
    assert len(real_failure_calls) == 0
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_spawn_with_retry_real_failure_invokes_callback():
    """Real failure must invoke on_real_failure exactly once."""
    real_failure_calls: list[Any] = []

    async def spawn_fn() -> dict[str, Any]:
        return {
            "exit_code": 1,
            "stderr": "SyntaxError: bad input",
            "duration_ms": 100,
            "work_events": 0,
            "cost_usd": 0.01,
        }

    result = await infra_error.spawn_with_retry(
        spawn_fn,
        feature_id="ic-real-fail-feat",
        job_name="ic-real-fail",
        sleep_fn=asyncio.sleep,
        probe_fn=lambda: True,
        on_real_failure=real_failure_calls.append,
    )
    assert result["exit_code"] == 1
    assert len(real_failure_calls) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_mid_work_crash_invokes_callback():
    """Mid-work crash must invoke on_mid_work_crash exactly once."""
    mid_crash_calls: list[Any] = []

    async def spawn_fn() -> dict[str, Any]:
        return {
            "exit_code": 1,
            "stderr": "fatal error in message reader",
            "duration_ms": 1000,
            "work_events": 0,
            "cost_usd": 0.01,
        }

    result = await infra_error.spawn_with_retry(
        spawn_fn,
        feature_id="ic-mid-crash-feat",
        job_name="ic-mid-crash",
        sleep_fn=asyncio.sleep,
        probe_fn=lambda: True,
        on_mid_work_crash=mid_crash_calls.append,
    )
    assert result["exit_code"] == 1
    assert len(mid_crash_calls) == 1


# ---------------------------------------------------------------------------
# No budget counter mutation on transient retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_retries_do_not_increment_budget():
    """Transient retries must not call on_real_failure or on_mid_work_crash."""
    budget_calls: list[str] = []

    async def spawn_fn() -> dict[str, Any]:
        budget_calls.append("spawn")
        if len(budget_calls) < 4:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 50, "work_events": 0, "cost_usd": 0.01}

    real_failure_calls: list[Any] = []
    mid_crash_calls: list[Any] = []

    async def instant_sleep(_: float) -> None:
        pass

    result = await infra_error.spawn_with_retry(
        spawn_fn,
        feature_id="no-budget-feat",
        job_name="no-budget",
        sleep_fn=instant_sleep,
        probe_fn=lambda: True,
        on_real_failure=real_failure_calls.append,
        on_mid_work_crash=mid_crash_calls.append,
    )
    assert result["exit_code"] == 0
    assert len(real_failure_calls) == 0
    assert len(mid_crash_calls) == 0
