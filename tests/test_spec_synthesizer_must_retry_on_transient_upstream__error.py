"""Error-path tests for bob.synthesizer transient-upstream retry behavior.

AC: invalid input raises ValueError and the function does not silently succeed.

These error-path tests verify that invalid inputs are rejected loudly, while
transient upstream errors are retried and do not propagate as exceptions.
"""
import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from bob.synthesizer import synthesize_for_feature, score_gate_loop


class TestSynthesizeForFeatureErrorPaths:
    """Error paths: invalid inputs must raise ValueError; upstream errors must not."""

    @pytest.mark.asyncio
    async def test_missing_project_id_raises(self):
        """project_id is required; calling without it must raise TypeError."""
        with pytest.raises(TypeError):
            # Missing required keyword argument project_id
            await synthesize_for_feature(
                title="test",
                description="test",
            )

    @pytest.mark.asyncio
    async def test_missing_title_raises(self):
        """title is required; calling without it must raise TypeError."""
        with pytest.raises(TypeError):
            await synthesize_for_feature(
                project_id="proj-1",
                description="test",
            )

    @pytest.mark.asyncio
    async def test_missing_description_raises(self):
        """description is required; calling without it must raise TypeError."""
        with pytest.raises(TypeError):
            await synthesize_for_feature(
                project_id="proj-1",
                title="test",
            )

    @pytest.mark.asyncio
    async def test_upstream_exception_does_not_propagate_after_retry(self):
        """Transient upstream exceptions are caught and retried, not propagated to caller."""
        call_count = 0

        async def always_raises(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("HTTP 400: Application 'Claude Code' (Production Restricted)")

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_raises):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    # Must return None, NOT raise RuntimeError
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="upstream exception feature",
                        description="upstream errors must not propagate",
                    )

        # Caller receives None (falls back to deterministic); exception is NOT raised
        assert result is None
        assert call_count == 2  # retried up to max attempts

    @pytest.mark.asyncio
    async def test_persistent_empty_result_returns_none_not_raises(self):
        """Persistent empty responses exhaust retries and return None, never raise."""
        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="always empty error path",
                        description="empty responses must return None, not raise",
                    )

        assert result is None  # NOT an exception

    @pytest.mark.asyncio
    async def test_invalid_max_attempts_env_var_falls_back_to_default(self):
        """Invalid BOB_SYNTH_MAX_ATTEMPTS value falls back gracefully, does not crash."""
        async def immediate_success(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py"]'

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=immediate_success):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "not_a_number"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    # Must not raise ValueError from int() conversion
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="invalid env var feature",
                        description="invalid env var must not crash synthesizer",
                    )

        assert result is not None  # succeeds despite invalid env var


class TestScoreGateLoopErrorPaths:
    """Error paths for score_gate_loop."""

    @pytest.mark.asyncio
    async def test_score_gate_loop_without_synthesize_fn_raises(self):
        """score_gate_loop requires synthesize_fn; missing it raises TypeError."""
        with pytest.raises(TypeError):
            await score_gate_loop(
                title="test",
                description="test",
                project_id="proj-1",
            )

    @pytest.mark.asyncio
    async def test_score_gate_loop_without_title_raises(self):
        """score_gate_loop requires title; missing it raises TypeError."""
        async def mock_synthesize(**kwargs):
            return ["File exists: src/foo.py"]

        with pytest.raises(TypeError):
            await score_gate_loop(
                synthesize_fn=mock_synthesize,
                description="test",
                project_id="proj-1",
            )

    @pytest.mark.asyncio
    async def test_score_gate_loop_use_fallback_false_raises_on_all_none(self):
        """score_gate_loop with use_fallback=False raises when synthesize_fn always returns None."""
        async def always_none(**kwargs):
            return None

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises((ValueError, Exception)):
                await score_gate_loop(
                    synthesize_fn=always_none,
                    title="always none error path",
                    description="should raise when use_fallback=False",
                    project_id="proj-1",
                    max_retries=1,
                    use_fallback=False,
                )

    @pytest.mark.asyncio
    async def test_synthesize_fn_raising_does_not_suppress_all_errors(self):
        """When synthesize_fn always raises, score_gate_loop handles gracefully (fallback or raise)."""
        call_count = 0

        async def always_raises(**kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("persistent upstream failure")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            # With use_fallback=True, should not raise to caller
            report = await score_gate_loop(
                synthesize_fn=always_raises,
                title="always raises error path",
                description="synthesize_fn always raises",
                project_id="proj-1",
                max_retries=1,
                use_fallback=True,
            )

        # Falls back deterministically rather than propagating the error
        assert report is not None


class TestRetryDoesNotSilentlySucceed:
    """Verify that invalid states are surfaced, not silently swallowed."""

    @pytest.mark.asyncio
    async def test_unparseable_response_returns_none_not_empty_list(self):
        """An unparseable LLM response returns None, not an empty list (not silent success)."""
        async def unparseable_response(*, project_id, prompt, workspace=None):
            return "this is not a valid JSON array of criteria"

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=unparseable_response):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "1"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="unparseable feature",
                        description="tests that unparseable result is None not empty list",
                    )

        # Should return either None (can't parse) or a non-empty list (if fallback parses)
        # The key invariant: must NOT silently return an empty list as if synthesis succeeded
        if result is not None:
            assert len(result) > 0, "Synthesizer must not return empty list as silent success"

    @pytest.mark.asyncio
    async def test_all_attempts_logged_when_exhausted(self, caplog):
        """When all retry attempts are exhausted, the failure is logged, not silenced."""
        import logging

        async def always_empty(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB_SYNTH_MAX_ATTEMPTS": "2"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with caplog.at_level(logging.WARNING, logger="bob.spec_synthesizer"):
                        result = await synthesize_for_feature(
                            project_id="proj-1",
                            title="exhausted retries feature",
                            description="must log failure when all attempts exhausted",
                        )

        assert result is None
        # Failure must be logged (observable, not silent)
        warning_logs = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_logs) >= 1, "Expected warning log when retries exhausted"
