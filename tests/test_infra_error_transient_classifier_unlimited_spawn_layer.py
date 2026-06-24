"""Tests for feature 8f042049: Infra-error transient classifier + unlimited
spawn-layer recovery (no budget impact) — short-named module.

Covers:
- classify_exit returns "transient" for HTTP 429, rate-limit, ECONNRESET,
  ETIMEDOUT, ENOENT/claude, shared-API-key marker.
- classify_exit returns "mid_work_crash" when work_events > 0 and no transient marker.
- classify_exit returns "real_failure" for generic non-transient exits.
- The public entry-point function is importable and callable.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import bob.infra_error_transient_classifier_unlimited_spawn_layer as mod


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
# Public entry-point function — AC-mandated test
# ---------------------------------------------------------------------------


def test_infra_error_transient_classifier_unlimited_spawn_layer() -> None:
    """AC-mandated bare test: the public entry-point function classifies exits correctly."""
    fn = mod.infra_error_transient_classifier_unlimited_spawn_layer

    assert callable(fn)

    # Transient infra error
    assert fn(exit_code=1, stderr="HTTP 429 Too Many Requests") == "transient"
    # Real failure
    assert fn(exit_code=1, stderr="implementation bug") == "real_failure"
    # Mid-work crash
    assert fn(exit_code=1, stderr="unrelated", work_events=5, duration_ms=10_000) == "mid_work_crash"
    # JSONL serialisation race → transient
    assert fn(exit_code=1, stderr="unrelated", work_events=3, duration_ms=0) == "transient"


# ---------------------------------------------------------------------------
# classify_exit — transient patterns
# ---------------------------------------------------------------------------


class TestClassifyExitTransient:
    def test_http_429_is_transient(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="HTTP 429 Too Many Requests")
        assert result == "transient"

    def test_rate_limit_is_transient(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="Error: rate limit exceeded")
        assert result == "transient"

    def test_econnreset_is_transient(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="ECONNRESET on socket")
        assert result == "transient"

    def test_etimedout_is_transient(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="connect ETIMEDOUT 10.0.0.1")
        assert result == "transient"

    def test_enoent_claude_is_transient(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="spawn ENOENT: no such file or directory, claude")
        assert result == "transient"

    def test_shared_api_key_marker_is_transient(self) -> None:
        result = mod.classify_exit(
            exit_code=1,
            stderr="shared API key and is being deprecated; subsequent requests will continue",
        )
        assert result == "transient"


# ---------------------------------------------------------------------------
# classify_exit — mid_work_crash
# ---------------------------------------------------------------------------


class TestClassifyExitMidWorkCrash:
    def test_work_events_with_no_transient_marker_is_mid_work_crash(self) -> None:
        result = mod.classify_exit(
            exit_code=1,
            stderr="some generic error",
            work_events=5,
            duration_ms=10_000,
        )
        assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# classify_exit — real_failure
# ---------------------------------------------------------------------------


class TestClassifyExitRealFailure:
    def test_generic_exit_1_no_marker_is_real_failure(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="implementation bug")
        assert result == "real_failure"


# ---------------------------------------------------------------------------
# spawn_with_retry — transient retry does not charge budget
# ---------------------------------------------------------------------------


class TestSpawnWithRetryTransient:
    def test_retries_until_success_without_calling_callbacks(self) -> None:
        call_count = {"n": 0}
        real_failure_calls: list[dict] = []

        async def spawn_fn() -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] < 3:
                return _make_result(exit_code=1, stderr="HTTP 429 Too Many Requests")
            return _make_result(exit_code=0)

        result = asyncio.run(
            mod.spawn_with_retry(
                spawn_fn,
                feature_id="test-feature",
                job_name="test-job",
                on_real_failure=real_failure_calls.append,
                sleep_fn=lambda _: asyncio.sleep(0),
                probe_fn=lambda: True,
            )
        )

        assert result["exit_code"] == 0
        assert call_count["n"] == 3
        assert real_failure_calls == []


# ---------------------------------------------------------------------------
# Public entry-point importable
# ---------------------------------------------------------------------------


class TestPublicEntryPoint:
    def test_function_is_importable(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer
        assert callable(fn)

    def test_function_returns_classify_result(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer
        result = fn(exit_code=1, stderr="HTTP 429 Too Many Requests")
        assert result == "transient"

    def test_function_returns_real_failure(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer
        result = fn(exit_code=1, stderr="some implementation bug")
        assert result == "real_failure"

    def test_function_returns_mid_work_crash(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer
        result = fn(exit_code=1, stderr="unrelated", work_events=5, duration_ms=10_000)
        assert result == "mid_work_crash"
