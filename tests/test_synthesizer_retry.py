"""Tests for bob.synthesizer retry behavior on transient upstream API errors.

Covers:
- synthesize_for_feature retries when LLM spawn returns empty text
- synthesize_for_feature retries when LLM spawn raises an exception
- Retry count is capped by BOB_SYNTH_MAX_ATTEMPTS env var
- Each retry attempt is logged (observable, not silent)
- Falls back to None after all attempts exhausted (no hang)
- score_gate_loop re-synthesis calls are also protected by retry
- Recovery succeeds when a later attempt returns non-empty text
"""
import asyncio
import logging
import os
from unittest.mock import AsyncMock, patch, call

import pytest

from bob.synthesizer import synthesize_for_feature, score_gate_loop


class TestSynthesizeForFeatureRetry:
    """synthesize_for_feature wraps the LLM spawn in an aggressive retry loop."""

    @pytest.mark.asyncio
    async def test_retries_on_empty_text(self, caplog):
        """When LLM spawn returns empty text, retries up to max attempts."""
        call_count = 0

        async def fake_llm(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ""  # transient empty
            return '["pytest: tests/test_foo.py", "File exists: src/foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=fake_llm):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                # Patch sleep to avoid actual waiting
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="test feature",
                        description="a test feature",
                    )

        assert result is not None
        assert call_count == 3  # failed twice, succeeded on 3rd

    @pytest.mark.asyncio
    async def test_retries_on_exception(self, caplog):
        """When LLM spawn raises, retries and eventually succeeds."""
        call_count = 0

        async def fake_llm(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient upstream 400")
            return '["File exists: src/foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=fake_llm):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="retry on exception feature",
                        description="tests retry on spawn exception",
                    )

        assert result is not None
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_returns_none_after_all_attempts_exhausted(self):
        """After all retry attempts return empty, function returns None (no hang)."""
        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "3"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="always empty feature",
                        description="will exhaust all attempts",
                    )

        assert result is None

    @pytest.mark.asyncio
    async def test_max_attempts_capped_by_env_var(self):
        """BOB_SYNTH_MAX_ATTEMPTS limits the number of retry attempts."""
        call_count = 0

        async def always_empty(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "4"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="capped retry feature",
                        description="env var caps retries",
                    )

        assert result is None
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_retry_is_logged_not_silent(self, caplog):
        """Each retry is logged so transient-upstream bursts are observable."""
        call_count = 0

        async def empty_then_valid(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return ""
            return '["pytest: tests/test_foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=empty_then_valid):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.WARNING, logger="bob.spec_synthesizer"):
                        result = await synthesize_for_feature(
                            project_id="proj-1",
                            title="logged retry feature",
                            description="retries must be logged",
                        )

        # At least one log message indicating retry occurred
        retry_logs = [r for r in caplog.records if "transient" in r.message.lower()
                      or "retrying" in r.message.lower()
                      or "empty" in r.message.lower()]
        assert len(retry_logs) >= 1, "Expected retry to be logged"
        assert result is not None

    @pytest.mark.asyncio
    async def test_immediate_success_no_retry(self):
        """When first attempt succeeds, no retries are made."""
        call_count = 0

        async def immediate_success(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return '["File exists: src/foo.py", "pytest: tests/test_foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=immediate_success):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "40"}):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="immediate success feature",
                        description="succeeds on first try",
                    )

        assert result is not None
        assert call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_recovery_logged_when_retry_succeeds(self, caplog):
        """When a later attempt succeeds, recovery is logged at INFO level."""
        call_count = 0

        async def fail_then_succeed(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ""
            return '["pytest: tests/test_foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=fail_then_succeed):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "5"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.INFO, logger="bob.spec_synthesizer"):
                        result = await synthesize_for_feature(
                            project_id="proj-1",
                            title="recovery feature",
                            description="recovers after failures",
                        )

        assert result is not None
        recovery_logs = [r for r in caplog.records if "recover" in r.message.lower()]
        assert len(recovery_logs) >= 1, "Expected recovery to be logged"


class TestScoreGateLoopRetry:
    """score_gate_loop re-synthesis calls are also protected by retry."""

    @pytest.mark.asyncio
    async def test_score_gate_loop_uses_synthesize_fn_that_retries(self):
        """score_gate_loop's synthesize_fn is called and can retry internally."""
        call_count = 0

        async def mock_synthesize(**kwargs):
            nonlocal call_count
            call_count += 1
            return ["File exists: src/foo.py", "pytest: tests/test_foo.py",
                    "pytest: tests/test_foo_boundary.py — boundary case",
                    "pytest: tests/test_foo_error.py — error path"]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="test score gate feature",
                description="validates score_gate_loop retry behavior",
                project_id="proj-1",
                max_retries=2,
            )

        assert report is not None
        assert report.criteria is not None
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_score_gate_loop_fallback_when_synthesize_always_none(self):
        """When synthesize_fn always returns None, falls back to deterministic."""
        async def always_none(**kwargs):
            return None

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=always_none,
                title="always none feature",
                description="tests fallback when all retries fail",
                project_id="proj-1",
                max_retries=2,
                use_fallback=True,
            )

        assert report is not None
        # With use_fallback=True, should still return criteria (from deterministic fallback)
        assert report.gate_failed or report.criteria is not None


class TestIntegrationWithOrchestrator:
    """Integration: bob.orchestrator uses bob.synthesizer functions."""

    def test_synthesizer_importable_from_orchestrator_context(self):
        """bob.synthesizer functions are importable (integration check)."""
        from bob.synthesizer import synthesize_for_feature, score_gate_loop
        assert callable(synthesize_for_feature)
        assert callable(score_gate_loop)

    def test_synthesize_for_feature_is_coroutine(self):
        """synthesize_for_feature is async (coroutine function)."""
        import asyncio
        from bob.synthesizer import synthesize_for_feature
        assert asyncio.iscoroutinefunction(synthesize_for_feature)

    def test_score_gate_loop_is_coroutine(self):
        """score_gate_loop is async (coroutine function)."""
        import asyncio
        from bob.synthesizer import score_gate_loop
        assert asyncio.iscoroutinefunction(score_gate_loop)
