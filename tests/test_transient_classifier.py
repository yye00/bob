"""Tests for bob3.transient_classifier — canonical transient-error module.

Verifies:
- classify_exit and spawn_with_retry are importable from bob3.transient_classifier
- classify_exit returns "transient" for known infra-error signatures
- classify_exit returns "real_failure" for non-transient exits
- classify_exit returns "mid_work_crash" for crashes after real work
- spawn_with_retry retries on transient exits and succeeds on success
"""

from __future__ import annotations

import pytest

import bob3.transient_classifier as mod
from bob3.transient_classifier import classify_exit, spawn_with_retry


# ---------------------------------------------------------------------------
# Module-level sanity
# ---------------------------------------------------------------------------


def test_module_exports_classify_exit():
    """classify_exit must be importable from bob3.transient_classifier."""
    assert callable(classify_exit)


def test_module_exports_spawn_with_retry():
    """spawn_with_retry must be importable from bob3.transient_classifier."""
    assert callable(spawn_with_retry)


# ---------------------------------------------------------------------------
# classify_exit — transient signatures
# ---------------------------------------------------------------------------


def test_classify_exit_http_429_is_transient():
    """HTTP 429 in stderr must yield 'transient'."""
    result = classify_exit(exit_code=1, stderr="Error: HTTP 429 Too Many Requests")
    assert result == "transient"


def test_classify_exit_rate_limit_is_transient():
    """rate limit in stderr must yield 'transient'."""
    result = classify_exit(exit_code=1, stderr="Error: rate limit exceeded")
    assert result == "transient"


def test_classify_exit_econnreset_is_transient():
    """ECONNRESET in stderr must yield 'transient'."""
    result = classify_exit(exit_code=1, stderr="read ECONNRESET")
    assert result == "transient"


def test_classify_exit_etimedout_is_transient():
    """ETIMEDOUT in stderr must yield 'transient'."""
    result = classify_exit(exit_code=1, stderr="connect ETIMEDOUT")
    assert result == "transient"


def test_classify_exit_enoent_claude_is_transient():
    """ENOENT for claude binary must yield 'transient'."""
    result = classify_exit(exit_code=1, stderr="spawn /usr/bin/claude ENOENT")
    assert result == "transient"


# ---------------------------------------------------------------------------
# classify_exit — non-transient exits
# ---------------------------------------------------------------------------


def test_classify_exit_real_failure_for_generic_error():
    """Generic non-matching stderr must yield 'real_failure'."""
    result = classify_exit(exit_code=1, stderr="AssertionError: expected True got False")
    assert result == "real_failure"


def test_classify_exit_success_exit_code_is_real_failure():
    """exit_code=0 is a successful exit; classify as 'real_failure' bucket (not a retry)."""
    result = classify_exit(exit_code=0, stderr="")
    assert result == "real_failure"


# ---------------------------------------------------------------------------
# classify_exit — mid_work_crash
# ---------------------------------------------------------------------------


def test_classify_exit_mid_work_crash_with_work_events():
    """work_events > 0 with no transient marker and duration > 0 yields 'mid_work_crash'."""
    result = classify_exit(exit_code=1, stderr="unexpected exit", work_events=5, duration_ms=1000)
    assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# spawn_with_retry — integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_returns_on_success():
    """spawn_with_retry must return immediately when spawn callable succeeds."""

    async def spawn_fn():
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.01}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-feature-id",
        job_name="test-job",
        sleep_fn=None,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_on_transient_then_succeeds():
    """spawn_with_retry must retry on TRANSIENT classification until success."""
    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return {"exit_code": 1, "stderr": "ECONNRESET", "duration_ms": 0, "work_events": 0, "cost_usd": 0.0}
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 1, "cost_usd": 0.02}

    async def no_sleep(_s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-retry-feature",
        job_name="test-retry-job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
    assert call_count == 3
