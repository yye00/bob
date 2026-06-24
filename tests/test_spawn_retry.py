"""Tests for bob3.spawn_retry — infra-error transient classifier + spawn-layer recovery.

Covers:
- classify_exit returns "transient" for HTTP 429, rate-limit, ECONNRESET,
  ETIMEDOUT, ENOENT/claude, shared-API-key deprecation marker.
- classify_exit returns "mid_work_crash" when work_events > 0 with no transient marker.
- classify_exit returns "real_failure" for generic non-transient exits.
- classify_exit reclassifies work_events > 0 + duration_ms == 0 as "transient".
- classify_exit returns "real_failure" for exit_code == 0 (clean exit).
- spawn_with_retry retries unlimited times on transient without calling
  on_real_failure or on_mid_work_crash (no budget impact).
- spawn_with_retry calls on_real_failure exactly once on real_failure.
- spawn_with_retry calls on_mid_work_crash exactly once on mid_work_crash.
- spawn_with_retry returns immediately on exit_code == 0.
- load_patterns returns default patterns when config path is missing.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bob3.spawn_retry import classify_exit, load_patterns, spawn_with_retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    exit_code: int = 1,
    stderr: str = "",
    duration_ms: int = 0,
    work_events: int = 0,
    cost_usd: float = 0.0,
) -> dict[str, Any]:
    return {
        "exit_code": exit_code,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "work_events": work_events,
        "cost_usd": cost_usd,
    }


# ---------------------------------------------------------------------------
# classify_exit — transient patterns
# ---------------------------------------------------------------------------


class TestClassifyExitTransient:
    def test_http_429_is_transient(self) -> None:
        result = classify_exit(exit_code=1, stderr="HTTP 429 Too Many Requests")
        assert result == "transient"

    def test_rate_limit_is_transient(self) -> None:
        result = classify_exit(exit_code=1, stderr="rate-limit exceeded")
        assert result == "transient"

    def test_econnreset_is_transient(self) -> None:
        result = classify_exit(exit_code=1, stderr="ECONNRESET: socket hang up")
        assert result == "transient"

    def test_etimedout_is_transient(self) -> None:
        result = classify_exit(exit_code=1, stderr="ETIMEDOUT: connection timed out")
        assert result == "transient"

    def test_enoent_claude_is_transient(self) -> None:
        result = classify_exit(
            exit_code=1, stderr="spawn ENOENT: No such file or directory, spawn 'claude'"
        )
        assert result == "transient"

    def test_shared_api_key_deprecated_is_transient(self) -> None:
        result = classify_exit(
            exit_code=1,
            stderr="Application 'Claude Code' is a shared API key and is being deprecated",
        )
        assert result == "transient"

    def test_work_events_positive_duration_zero_is_transient(self) -> None:
        """JSONL serialisation race / SIGPIPE: work_events > 0 + duration_ms == 0 → transient."""
        result = classify_exit(exit_code=1, stderr="", work_events=3, duration_ms=0)
        assert result == "transient"


# ---------------------------------------------------------------------------
# classify_exit — mid_work_crash
# ---------------------------------------------------------------------------


class TestClassifyExitMidWorkCrash:
    def test_positive_work_events_no_transient_marker_is_mid_work_crash(self) -> None:
        result = classify_exit(exit_code=1, stderr="some unknown error", work_events=5, duration_ms=1000)
        assert result == "mid_work_crash"

    def test_message_reader_crashed_is_mid_work_crash(self) -> None:
        result = classify_exit(exit_code=1, stderr="fatal error in message reader")
        assert result == "mid_work_crash"

    def test_shutdown_crash_marker_is_mid_work_crash(self) -> None:
        result = classify_exit(exit_code=1, stderr="shutdown crash occurred")
        assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# classify_exit — real_failure
# ---------------------------------------------------------------------------


class TestClassifyExitRealFailure:
    def test_generic_error_no_work_is_real_failure(self) -> None:
        result = classify_exit(exit_code=1, stderr="SyntaxError: unexpected token")
        assert result == "real_failure"

    def test_zero_exit_code_is_real_failure(self) -> None:
        """exit_code == 0 is a clean exit; classify_exit marks it real_failure (callers treat as success)."""
        result = classify_exit(exit_code=0, stderr="")
        assert result == "real_failure"

    def test_empty_stderr_no_work_is_real_failure(self) -> None:
        result = classify_exit(exit_code=1, stderr="")
        assert result == "real_failure"


# ---------------------------------------------------------------------------
# load_patterns
# ---------------------------------------------------------------------------


def test_load_patterns_missing_config_returns_defaults() -> None:
    patterns = load_patterns("/nonexistent/path/spawn_retry.yaml")
    assert len(patterns) > 0


def test_load_patterns_default_contains_429() -> None:
    patterns = load_patterns("/nonexistent/path")
    combined = " ".join(p.pattern for p in patterns)
    assert "429" in combined


# ---------------------------------------------------------------------------
# spawn_with_retry — no budget impact on transient retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_transient_without_budget_impact() -> None:
    """Transient errors retry unlimited times; on_real_failure/on_mid_work_crash never called."""
    call_count = 0

    async def spawn_fn() -> dict:
        nonlocal call_count
        call_count += 1
        if call_count < 4:
            return _make_result(exit_code=1, stderr="HTTP 429 Too Many Requests")
        return _make_result(exit_code=0, stderr="", duration_ms=500, work_events=1)

    real_failure_calls: list = []
    mid_crash_calls: list = []

    async def no_sleep(_s: float) -> None:
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-transient-no-budget",
        job_name="test_transient",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_calls.append(r),
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
    )

    assert result["exit_code"] == 0
    assert call_count == 4
    assert len(real_failure_calls) == 0, "on_real_failure must not be called for transient retries"
    assert len(mid_crash_calls) == 0, "on_mid_work_crash must not be called for transient retries"


@pytest.mark.asyncio
async def test_spawn_with_retry_calls_on_real_failure_once() -> None:
    """on_real_failure is invoked exactly once on a real_failure outcome."""

    async def spawn_fn() -> dict:
        return _make_result(exit_code=1, stderr="SyntaxError: unexpected token")

    real_failure_calls: list = []

    async def no_sleep(_s: float) -> None:
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-real-failure",
        job_name="test_real_failure",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_calls.append(r),
    )

    assert result["exit_code"] == 1
    assert len(real_failure_calls) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_calls_on_mid_work_crash_once() -> None:
    """on_mid_work_crash is invoked exactly once on a mid_work_crash outcome."""

    async def spawn_fn() -> dict:
        return _make_result(exit_code=1, stderr="unknown error", work_events=5, duration_ms=1000)

    mid_crash_calls: list = []

    async def no_sleep(_s: float) -> None:
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-mid-crash",
        job_name="test_mid_crash",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
    )

    assert result["exit_code"] == 1
    assert len(mid_crash_calls) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_returns_immediately_on_success() -> None:
    """exit_code == 0 returns immediately on first attempt."""

    async def spawn_fn() -> dict:
        return _make_result(exit_code=0, stderr="", duration_ms=500, work_events=2)

    async def no_sleep(_s: float) -> None:
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="test-immediate-success",
        job_name="test_success",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    assert result["exit_code"] == 0
