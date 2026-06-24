"""Tests for feature 5e3e0c6b: Infra-error transient classifier + unlimited
spawn-layer recovery (no budget impact).

Covers:
- classify_exit returns "transient" for HTTP 429, rate-limit, ECONNRESET,
  ETIMEDOUT, ENOENT/claude, shared-API-key marker.
- classify_exit returns "mid_work_crash" when work_events > 0 and no transient marker.
- classify_exit returns "real_failure" for generic non-transient exits.
- classify_exit reclassifies work_events > 0 + duration_ms == 0 as "transient".
- spawn_with_retry retries unlimited times on transient without calling
  on_real_failure or on_mid_work_crash.
- spawn_with_retry calls on_real_failure exactly once on real_failure.
- spawn_with_retry calls on_mid_work_crash exactly once on mid_work_crash.
- spawn_with_retry does not increment any external budget counter on transient
  retries (verified by tracking on_real_failure / on_mid_work_crash call counts).
- The public entry-point function is importable and callable.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import bob.infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact as mod


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

    def test_rate_limit_case_insensitive(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="RATE.LIMIT violation")
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

    def test_message_reader_fatal_error_is_mid_work_crash(self) -> None:
        result = mod.classify_exit(
            exit_code=1,
            stderr="Fatal error in message reader",
            work_events=0,
            duration_ms=0,
        )
        assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# classify_exit — real_failure
# ---------------------------------------------------------------------------


class TestClassifyExitRealFailure:
    def test_generic_exit_1_no_marker_is_real_failure(self) -> None:
        result = mod.classify_exit(exit_code=1, stderr="implementation bug")
        assert result == "real_failure"

    def test_exit_0_is_returned_as_real_failure_sentinel(self) -> None:
        # exit_code=0 is the success path; classify_exit signals "real_failure"
        # as the sentinel so callers treat exit_code=0 differently.
        result = mod.classify_exit(exit_code=0, stderr="")
        assert result == "real_failure"


# ---------------------------------------------------------------------------
# classify_exit — JSONL serialisation race reclassification
# ---------------------------------------------------------------------------


class TestClassifyExitJSONLRace:
    def test_work_events_with_duration_zero_is_transient(self) -> None:
        result = mod.classify_exit(
            exit_code=1,
            stderr="some unrelated error",
            work_events=3,
            duration_ms=0,
        )
        assert result == "transient"

    def test_work_events_with_nonzero_duration_is_mid_work_crash(self) -> None:
        result = mod.classify_exit(
            exit_code=1,
            stderr="unrelated",
            work_events=3,
            duration_ms=5_000,
        )
        assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# spawn_with_retry — transient retry does not charge budget
# ---------------------------------------------------------------------------


class TestSpawnWithRetryTransient:
    def test_retries_until_success_without_calling_callbacks(self) -> None:
        """Transient errors retry silently; callbacks are not invoked."""
        call_count = {"n": 0}
        real_failure_calls: list[dict] = []
        mid_work_crash_calls: list[dict] = []

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
                on_mid_work_crash=mid_work_crash_calls.append,
                sleep_fn=lambda _: asyncio.sleep(0),
                probe_fn=lambda: True,
            )
        )

        assert result["exit_code"] == 0
        assert call_count["n"] == 3
        assert real_failure_calls == []
        assert mid_work_crash_calls == []

    def test_no_budget_impact_on_transient(self) -> None:
        """on_real_failure is never called for transient retries."""
        budget_hits: list[dict] = []
        call_count = {"n": 0}

        async def spawn_fn() -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] < 4:
                return _make_result(exit_code=1, stderr="ECONNRESET")
            return _make_result(exit_code=0)

        asyncio.run(
            mod.spawn_with_retry(
                spawn_fn,
                feature_id="feat-budget",
                job_name="budget-test",
                on_real_failure=budget_hits.append,
                sleep_fn=lambda _: asyncio.sleep(0),
                probe_fn=lambda: True,
            )
        )

        assert budget_hits == []


# ---------------------------------------------------------------------------
# spawn_with_retry — non-transient outcomes invoke callbacks
# ---------------------------------------------------------------------------


class TestSpawnWithRetryCallbacks:
    def test_real_failure_calls_on_real_failure(self) -> None:
        real_failure_calls: list[dict] = []

        async def spawn_fn() -> dict[str, Any]:
            return _make_result(exit_code=1, stderr="implementation broke")

        asyncio.run(
            mod.spawn_with_retry(
                spawn_fn,
                feature_id="feat-real",
                job_name="real-fail",
                on_real_failure=real_failure_calls.append,
                sleep_fn=lambda _: asyncio.sleep(0),
                probe_fn=lambda: True,
            )
        )

        assert len(real_failure_calls) == 1

    def test_mid_work_crash_calls_on_mid_work_crash(self) -> None:
        mid_work_crash_calls: list[dict] = []

        async def spawn_fn() -> dict[str, Any]:
            return _make_result(
                exit_code=1,
                stderr="something broke",
                work_events=2,
                duration_ms=10_000,
            )

        asyncio.run(
            mod.spawn_with_retry(
                spawn_fn,
                feature_id="feat-mid",
                job_name="mid-crash",
                on_mid_work_crash=mid_work_crash_calls.append,
                sleep_fn=lambda _: asyncio.sleep(0),
                probe_fn=lambda: True,
            )
        )

        assert len(mid_work_crash_calls) == 1


# ---------------------------------------------------------------------------
# Public entry-point function
# ---------------------------------------------------------------------------


def test_infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact() -> None:
    """AC-mandated bare test: the public entry-point function classifies exits correctly."""
    fn = mod.infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact

    assert callable(fn)

    # Transient infra error
    assert fn(exit_code=1, stderr="HTTP 429 Too Many Requests") == "transient"
    # Real failure
    assert fn(exit_code=1, stderr="implementation bug") == "real_failure"
    # Mid-work crash
    assert fn(exit_code=1, stderr="unrelated", work_events=5, duration_ms=10_000) == "mid_work_crash"
    # JSONL serialisation race → transient
    assert fn(exit_code=1, stderr="unrelated", work_events=3, duration_ms=0) == "transient"


class TestPublicEntryPoint:
    def test_function_is_importable(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact
        assert callable(fn)

    def test_function_returns_classify_result(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact
        result = fn(exit_code=1, stderr="HTTP 429 Too Many Requests")
        assert result == "transient"

    def test_function_returns_real_failure(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact
        result = fn(exit_code=1, stderr="some implementation bug")
        assert result == "real_failure"

    def test_function_returns_mid_work_crash(self) -> None:
        fn = mod.infra_error_transient_classifier_unlimited_spawn_layer_recovery_no_budget_impact
        result = fn(exit_code=1, stderr="unrelated", work_events=5, duration_ms=10_000)
        assert result == "mid_work_crash"
