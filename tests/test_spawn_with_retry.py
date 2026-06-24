"""Tests for the top-level spawn_with_retry module (src/spawn_with_retry.py).

Verifies that classify_exit and spawn_with_retry are importable from the
top-level module and behave correctly.
"""

from __future__ import annotations

import asyncio
import pytest

import spawn_with_retry as swr


def test_module_exports_classify_exit():
    assert callable(swr.classify_exit)


def test_module_exports_spawn_with_retry():
    assert callable(swr.spawn_with_retry)


def test_classify_exit_zero_is_not_transient():
    result = swr.classify_exit(exit_code=0, stderr=None)
    assert result == "real_failure"


def test_classify_exit_429_is_transient():
    result = swr.classify_exit(exit_code=1, stderr="HTTP 429 Too Many Requests")
    assert result == "transient"


def test_classify_exit_econnreset_is_transient():
    result = swr.classify_exit(exit_code=1, stderr="Error: ECONNRESET: socket hang up")
    assert result == "transient"


def test_classify_exit_etimedout_is_transient():
    result = swr.classify_exit(exit_code=1, stderr="ETIMEDOUT connecting to api.anthropic.com")
    assert result == "transient"


def test_classify_exit_real_failure():
    result = swr.classify_exit(exit_code=1, stderr="SyntaxError: unexpected EOF")
    assert result == "real_failure"


def test_classify_exit_work_events_without_output_is_mid_work_crash():
    result = swr.classify_exit(exit_code=1, stderr="unknown error", work_events=5, duration_ms=1000)
    assert result == "mid_work_crash"


def test_classify_exit_work_events_with_duration_zero_is_transient():
    # duration_ms == 0 with work_events > 0 → JSONL race / SIGPIPE → transient
    result = swr.classify_exit(exit_code=1, stderr="", work_events=3, duration_ms=0)
    assert result == "transient"


@pytest.mark.asyncio
async def test_spawn_with_retry_success_on_first_attempt():
    async def spawn_fn():
        return {"exit_code": 0, "stderr": "", "duration_ms": 500, "work_events": 0, "cost_usd": 0.01}

    result = await swr.spawn_with_retry(
        spawn_fn,
        feature_id="test-feat",
        job_name="test",
        sleep_fn=asyncio.sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_transient():
    calls = []

    async def spawn_fn():
        calls.append(len(calls))
        if len(calls) < 3:
            return {"exit_code": 1, "stderr": "429", "duration_ms": 0, "work_events": 0, "cost_usd": 0.0}
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.01}

    async def no_sleep(_s):
        pass

    result = await swr.spawn_with_retry(
        spawn_fn,
        feature_id="test-feat-2",
        job_name="test2",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
    assert len(calls) == 3
