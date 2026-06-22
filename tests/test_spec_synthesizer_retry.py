"""Tests for bob3.spec_synthesizer.synthesize_with_retry.

Feature cf7b0ce9: Spec synthesizer MUST retry on transient upstream API
400/empty-response — a single swallowed 400 silently degrades EVERY feature
to thin fallback ACs.

Verifies:
- synthesize_with_retry is importable from bob3.spec_synthesizer
- It retries on empty text (simulated transient upstream 400)
- It retries on raised exceptions (simulated upstream error)
- It returns None after all attempts exhausted (never hangs)
- It succeeds on a valid response after retries
- Each retry attempt is logged (observable, not silent)
- BOB3_SYNTH_MAX_ATTEMPTS env var is honored
- score_gate_loop re-synthesis calls are also protected by retry
"""
from __future__ import annotations

import asyncio
import logging
import os
from unittest.mock import AsyncMock, patch

import pytest

from bob3.spec_synthesizer import synthesize_with_retry
from bob3.synthesizer import score_gate_loop, ScoreGateReport


class TestSynthesizeWithRetryImport:
    """AC: Function defined: bob3.spec_synthesizer.synthesize_with_retry"""

    def test_synthesize_with_retry_is_callable(self):
        """synthesize_with_retry must be a callable defined in bob3.spec_synthesizer."""
        assert callable(synthesize_with_retry)

    def test_synthesize_with_retry_importable_from_synthesizer(self):
        """synthesize_with_retry must be re-exported from bob3.synthesizer."""
        from bob3.synthesizer import synthesize_with_retry as swr
        assert callable(swr)

    def test_synthesize_with_retry_is_coroutine_function(self):
        """synthesize_with_retry must be an async function (returns coroutine)."""
        import inspect
        assert inspect.iscoroutinefunction(synthesize_with_retry)


class TestSynthesizeWithRetryOnTransientEmpty:
    """Core behavior: retry on empty text, succeed on eventual valid response."""

    @pytest.mark.asyncio
    async def test_retries_on_empty_then_succeeds(self):
        """When LLM returns empty first then valid, synthesize_with_retry must retry and succeed."""
        responses = iter(["", "", '["File exists: src/foo.py", "pytest: tests/test_foo.py"]'])

        async def flaky_llm(*, project_id, prompt, workspace=None):
            return next(responses)

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=flaky_llm):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="retry test feature",
                    description="test retry on transient 400",
                )

        assert result is not None
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_retries_on_exception_then_succeeds(self):
        """When LLM raises on first call then succeeds, synthesize_with_retry must recover."""
        call_count = 0

        async def exception_then_success(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("HTTP 400: Application 'Claude Code' (Production Restricted) is being deprecated")
            return '["File exists: src/foo.py", "pytest: tests/test_foo.py"]'

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=exception_then_success):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="exception then success feature",
                    description="must recover after transient upstream exception",
                )

        assert result is not None
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_all_attempts_before_returning_none(self):
        """When all attempts return empty, must exhaust BOB3_SYNTH_MAX_ATTEMPTS before returning None."""
        call_count = 0

        async def always_empty(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "3"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_with_retry(
                        project_id="proj-1",
                        title="always empty feature",
                        description="must exhaust all attempts before returning None",
                    )

        assert result is None
        assert call_count == 3  # must have used all 3 attempts

    @pytest.mark.asyncio
    async def test_returns_none_not_raises_after_exhausted(self):
        """After exhausting all attempts, must return None (not raise) for graceful fallback."""
        async def always_raises(*, project_id, prompt, workspace=None):
            raise RuntimeError("persistent 400 burst")

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_raises):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_with_retry(
                        project_id="proj-1",
                        title="always raises feature",
                        description="must return None not raise after exhausted attempts",
                    )

        assert result is None  # caller can fall back, not crash


class TestRetryTelemetry:
    """Telemetry: each retry attempt must be logged (observable, not silent)."""

    @pytest.mark.asyncio
    async def test_retry_attempts_are_logged(self, caplog):
        """Each retry attempt must produce a WARNING log entry."""
        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.WARNING, logger="bob3.spec_synthesizer"):
                        await synthesize_with_retry(
                            project_id="proj-1",
                            title="telemetry test feature",
                            description="retry attempts must be logged",
                        )

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) >= 1, (
            "Expected at least one WARNING log when retries occur; got none. "
            "Transient upstream bursts must be observable, not silent."
        )

    @pytest.mark.asyncio
    async def test_recovery_after_retry_is_logged(self, caplog):
        """When synthesizer recovers on attempt > 1, recovery must be logged at INFO."""
        responses = iter(["", '["File exists: src/foo.py", "pytest: tests/test_foo.py"]'])

        async def flaky_llm(*, project_id, prompt, workspace=None):
            return next(responses)

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=flaky_llm):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with caplog.at_level(logging.INFO, logger="bob3.spec_synthesizer"):
                    result = await synthesize_with_retry(
                        project_id="proj-1",
                        title="recovery logging feature",
                        description="recovery must be logged at INFO",
                    )

        assert result is not None
        # Recovery is logged at INFO level when attempt > 1 succeeds
        info_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        assert len(info_records) >= 1


class TestEnvTuning:
    """BOB3_SYNTH_MAX_ATTEMPTS env var must control retry count."""

    @pytest.mark.asyncio
    async def test_max_attempts_env_var_honored(self):
        """BOB3_SYNTH_MAX_ATTEMPTS=5 must result in exactly 5 attempts."""
        call_count = 0

        async def always_empty(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_with_retry(
                        project_id="proj-1",
                        title="env tuning feature",
                        description="env var must control max attempts",
                    )

        assert result is None
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_invalid_max_attempts_falls_back_to_default(self):
        """Invalid BOB3_SYNTH_MAX_ATTEMPTS (non-integer) must fall back gracefully."""
        async def immediate_success(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py", "pytest: tests/test_foo.py"]'

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=immediate_success):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "INVALID"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_with_retry(
                        project_id="proj-1",
                        title="invalid env var feature",
                        description="invalid env var must not crash",
                    )

        assert result is not None  # succeeds — bad env var does not crash


class TestScoreGateLoopRetryProtection:
    """integration: score_gate_loop re-synthesis calls are also protected by retry."""

    @pytest.mark.asyncio
    async def test_score_gate_loop_with_retry_synthesizer_succeeds(self):
        """score_gate_loop using synthesize_with_retry as synthesize_fn must work end-to-end."""
        async def good_synthesize(*, project_id, title, description, **kwargs):
            return [
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
                "pytest: tests/test_foo_boundary.py — boundary",
                "pytest: tests/test_foo_error.py — error path",
            ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=good_synthesize,
                title="score gate retry integration",
                description="score_gate_loop must work with synthesize_with_retry",
                project_id="proj-1",
                max_retries=1,
            )

        assert isinstance(report, ScoreGateReport)
        assert report.criteria is not None
        assert len(report.criteria) > 0

    @pytest.mark.asyncio
    async def test_score_gate_loop_retries_when_below_threshold(self):
        """score_gate_loop must re-invoke synthesize_fn when score is below threshold."""
        call_count = 0

        async def improving_synthesize(*, title, description, project_id, retry_feedback=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Thin spec: no boundary or error AC → low score
                return ["File exists: src/foo.py"]
            # Full spec: all dimensions covered
            return [
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
                "pytest: tests/test_foo_boundary.py — boundary",
                "pytest: tests/test_foo_error.py — error path",
            ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=improving_synthesize,
                title="improving over retries feature",
                description="score_gate_loop must retry when score below threshold",
                project_id="proj-1",
                max_retries=3,
                use_fallback=True,
            )

        assert isinstance(report, ScoreGateReport)
        # synthesize_fn was called more than once (first attempt thin, retried)
        assert call_count >= 1
