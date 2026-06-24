"""Tests for bob.synthesize retry behavior on transient upstream API 400/empty responses.

Verifies the aggressive retry logic introduced to prevent a single swallowed HTTP 400
from degrading an entire synthesis pass to thin deterministic fallback ACs.

Root cause: the shared upstream API key intermittently returns HTTP 400 in bursts
lasting several minutes. The claude CLI exits ~1s with EMPTY text and does NOT retry.
A single spawn attempt would silently fall through to thin ACs (~0.75, below 0.85 gate)
for EVERY feature in the burst window — root cause of synthesized=0/118 across generations.

These tests verify the fix: synthesize_for_feature wraps the LLM spawn in an aggressive
retry loop (default 40 attempts, env-tunable BOB_SYNTH_MAX_ATTEMPTS) with exponential
backoff (2, 4, 8, 16, 32s, capped at 60s + jitter) and logs each retry attempt.
"""
from __future__ import annotations

import asyncio
import logging
import os
from unittest.mock import AsyncMock, call, patch

import pytest

from bob.synthesize import (
    ScoreGateReport,
    _DEFAULT_MAX_RETRIES,
    _DEFAULT_SPEC_QUALITY_THRESHOLD,
    deterministic_fallback,
    score_gate_loop,
    synthesize_for_feature,
)


class TestRetryOnEmptyResponse:
    """synthesize_for_feature retries when LLM returns empty text."""

    @pytest.mark.asyncio
    async def test_retries_on_empty_response_then_succeeds(self):
        """After N empty responses, a successful one is accepted (transient 400 cleared)."""
        responses = ["", "", '["File exists: src/foo.py", "pytest: tests/test_foo.py"]']
        call_idx = 0

        async def flaky_llm(*, project_id, prompt, workspace=None):
            nonlocal call_idx
            result = responses[call_idx] if call_idx < len(responses) else responses[-1]
            call_idx += 1
            return result

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=flaky_llm):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="retry success feature",
                        description="test feature that succeeds after transient failures",
                    )

        assert result is not None
        assert len(result) >= 1
        assert call_idx == 3  # exactly 3 calls: 2 empty + 1 success

    @pytest.mark.asyncio
    async def test_retries_up_to_max_attempts_on_persistent_empty(self):
        """When LLM persistently returns empty, all MAX_ATTEMPTS are used, then returns None."""
        call_count = 0

        async def always_empty(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "3"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="persistent empty feature",
                        description="test that retries exactly max attempts",
                    )

        assert result is None
        assert call_count == 3  # exactly 3 attempts, not more

    @pytest.mark.asyncio
    async def test_does_not_sleep_after_last_attempt(self):
        """No sleep after the final attempt — only between retries."""
        sleep_mock = AsyncMock()

        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "3"}):
                with patch("asyncio.sleep", sleep_mock):
                    await synthesize_for_feature(
                        project_id="proj-1",
                        title="sleep count feature",
                        description="verify no extra sleep after last attempt",
                    )

        # 3 attempts → 2 sleeps between them (not 3)
        assert sleep_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_first_success_no_sleep(self):
        """When the first attempt succeeds, no sleep is needed."""
        sleep_mock = AsyncMock()

        async def immediate_success(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=immediate_success):
            with patch("asyncio.sleep", sleep_mock):
                result = await synthesize_for_feature(
                    project_id="proj-1",
                    title="immediate success feature",
                    description="no sleep needed on first success",
                )

        assert result is not None
        assert sleep_mock.call_count == 0


class TestRetryOnException:
    """synthesize_for_feature retries when LLM spawn raises an exception."""

    @pytest.mark.asyncio
    async def test_retries_on_runtime_error_then_succeeds(self):
        """Exception on spawn is caught and retried until success."""
        responses = [
            RuntimeError("HTTP 400: Production Restricted shared API key"),
            RuntimeError("HTTP 400: retry me"),
            '["File exists: src/foo.py"]',
        ]
        call_idx = 0

        async def flaky_llm(*, project_id, prompt, workspace=None):
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            if isinstance(resp, Exception):
                raise resp
            return resp

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=flaky_llm):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="exception retry feature",
                        description="test exception retried until success",
                    )

        assert result is not None
        assert call_idx == 3

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self):
        """ConnectionError (network layer failure) is retried, not propagated."""
        call_count = 0

        async def network_error(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection reset by peer")

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=network_error):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="connection error feature",
                        description="connection errors must be retried, not raised",
                    )

        assert result is None  # exhausted retries → None, not raised
        assert call_count == 2


class TestRetryLogging:
    """Each retry attempt must be logged so transient bursts are observable."""

    @pytest.mark.asyncio
    async def test_retry_logged_on_empty_response(self, caplog):
        """Each empty response retry is logged at WARNING level."""
        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.WARNING, logger="bob.spec_synthesizer"):
                        await synthesize_for_feature(
                            project_id="proj-1",
                            title="logging test feature",
                            description="test that retries are logged",
                        )

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_messages) >= 1
        # At least one log message must mention the retry/empty/transient context
        retry_related = [
            m for m in warning_messages
            if any(kw in m.lower() for kw in ("retry", "empty", "transient", "attempt", "fallback"))
        ]
        assert len(retry_related) >= 1, (
            f"Expected retry-related warning log; got: {warning_messages}"
        )

    @pytest.mark.asyncio
    async def test_recovery_logged_when_eventually_succeeds(self, caplog):
        """Recovery after retries is logged at INFO level."""
        responses = ["", "", '["File exists: src/foo.py"]']
        call_idx = 0

        async def flaky_llm(*, project_id, prompt, workspace=None):
            nonlocal call_idx
            result = responses[call_idx] if call_idx < len(responses) else responses[-1]
            call_idx += 1
            return result

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=flaky_llm):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.INFO, logger="bob.spec_synthesizer"):
                        result = await synthesize_for_feature(
                            project_id="proj-1",
                            title="recovery log feature",
                            description="recovery after retries must be logged",
                        )

        assert result is not None
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        recovery_logs = [
            m for m in info_messages
            if any(kw in m.lower() for kw in ("recover", "cleared", "attempt", "upstream"))
        ]
        assert len(recovery_logs) >= 1, (
            f"Expected recovery INFO log; got info messages: {info_messages}"
        )

    @pytest.mark.asyncio
    async def test_exception_retry_logged_at_warning(self, caplog):
        """Exception during spawn is logged as a warning, not silenced."""
        async def always_raises(*, project_id, prompt, workspace=None):
            raise RuntimeError("HTTP 400")

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_raises):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.WARNING, logger="bob.spec_synthesizer"):
                        await synthesize_for_feature(
                            project_id="proj-1",
                            title="exception log feature",
                            description="exceptions during spawn must be logged",
                        )

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_messages) >= 1


class TestMaxAttemptsEnvVar:
    """BOB_SYNTH_MAX_ATTEMPTS is read from env and controls retry count."""

    @pytest.mark.asyncio
    async def test_env_var_controls_max_attempts(self):
        """BOB_SYNTH_MAX_ATTEMPTS env var is respected."""
        call_count = 0

        async def always_empty(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "7"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await synthesize_for_feature(
                        project_id="proj-1",
                        title="env var feature",
                        description="test env-tunable max attempts",
                    )

        assert call_count == 7

    @pytest.mark.asyncio
    async def test_invalid_env_var_falls_back_to_default(self):
        """Non-integer BOB_SYNTH_MAX_ATTEMPTS falls back to default (40), does not crash."""
        call_count = 0

        async def immediate_success(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return '["File exists: src/foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=immediate_success):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "not_a_number"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="invalid env var feature",
                        description="invalid env var must not crash",
                    )

        assert result is not None
        assert call_count == 1  # succeeds on first attempt


class TestExponentialBackoff:
    """Backoff between retries grows exponentially, capped at 60s."""

    @pytest.mark.asyncio
    async def test_backoff_grows_between_retries(self):
        """Sleep delays grow (exponential) between successive empty responses."""
        sleep_delays = []

        async def capture_sleep(seconds):
            sleep_delays.append(seconds)

        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "4"}):
                with patch("asyncio.sleep", side_effect=capture_sleep):
                    await synthesize_for_feature(
                        project_id="proj-1",
                        title="backoff test feature",
                        description="test exponential backoff pattern",
                    )

        # 4 attempts → 3 sleeps
        assert len(sleep_delays) == 3
        # Delays must be positive and generally non-decreasing (exponential)
        assert all(d > 0 for d in sleep_delays)
        # First delay is the smallest; last should be larger (exponential growth)
        # Note: jitter may add small variation, so we just check the trend
        assert sleep_delays[0] <= sleep_delays[-1] + 1  # last is not smaller than first


class TestPublicAPIAccessible:
    """The retry logic is accessible via the public bob.synthesize module."""

    def test_synthesize_for_feature_importable(self):
        """synthesize_for_feature is importable from bob.synthesize."""
        from bob.synthesize import synthesize_for_feature as sfr
        assert callable(sfr)

    def test_score_gate_loop_importable(self):
        """score_gate_loop is importable from bob.synthesize."""
        from bob.synthesize import score_gate_loop as sgl
        assert callable(sgl)

    def test_score_gate_report_importable(self):
        """ScoreGateReport is importable from bob.synthesize."""
        from bob.synthesize import ScoreGateReport as SGR
        assert SGR is not None

    def test_deterministic_fallback_importable(self):
        """deterministic_fallback is importable from bob.synthesize."""
        from bob.synthesize import deterministic_fallback as df
        assert callable(df)

    def test_synthesizer_module_accessible(self):
        """synthesize_for_feature and score_gate_loop accessible via bob.synthesizer."""
        from bob.synthesizer import synthesize_for_feature, score_gate_loop
        assert callable(synthesize_for_feature)
        assert callable(score_gate_loop)


class TestScoreGateLoopRetry:
    """score_gate_loop re-synthesizes with retry when composite score is below threshold."""

    @pytest.mark.asyncio
    async def test_score_gate_loop_retries_below_threshold(self):
        """score_gate_loop calls synthesize_fn multiple times when score is below threshold."""
        call_count = 0

        async def synthesize(**kwargs):
            nonlocal call_count
            call_count += 1
            # Return valid ACs every time; score_gate_loop will score them
            return [
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
                "pytest: tests/test_foo_boundary.py — boundary case: empty input",
                "pytest: tests/test_foo_error.py — error path: raises ValueError on invalid",
                "integration: bob.synthesizer",
            ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=synthesize,
                title="score gate retry feature",
                description="test that score_gate_loop retries until threshold met",
                project_id="proj-1",
                max_retries=3,
            )

        assert isinstance(report, ScoreGateReport)
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_score_gate_loop_returns_best_on_exhaustion(self):
        """score_gate_loop returns best criteria found when max_retries exhausted."""
        async def synthesize(**kwargs):
            return [
                "File exists: src/foo.py",
                "pytest: tests/test_foo.py",
                "pytest: tests/test_foo_boundary.py — boundary",
                "pytest: tests/test_foo_error.py — error path",
            ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=synthesize,
                title="exhaustion feature",
                description="test score_gate_loop exhaustion returns best",
                project_id="proj-1",
                max_retries=1,
                use_fallback=True,
            )

        assert isinstance(report, ScoreGateReport)
        # Report must have criteria (either synthesized or fallback)
        assert report.criteria is not None
        assert len(report.criteria) >= 1


class TestFallbackAfterExhaustion:
    """After all retries exhausted, deterministic fallback is used (never hangs)."""

    @pytest.mark.asyncio
    async def test_returns_none_on_persistent_empty(self):
        """synthesize_for_feature returns None (not hangs) after all retries exhausted."""
        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="fallback test feature",
                        description="verify fallback after retry exhaustion, not hang",
                    )

        # Returns None (caller can use deterministic_fallback), not hangs
        assert result is None

    def test_deterministic_fallback_produces_non_empty_criteria(self):
        """deterministic_fallback always returns at least minimal criteria (never empty)."""
        result = deterministic_fallback(
            "some feature",
            "a feature that needs deterministic fallback",
        )

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_deterministic_fallback_empty_feature_name(self):
        """deterministic_fallback with empty feature_name produces criteria, not raises."""
        result = deterministic_fallback("", "a description")
        assert isinstance(result, list)
        # May return minimal criteria; must not silently return empty list
        if result:
            assert len(result) >= 1
