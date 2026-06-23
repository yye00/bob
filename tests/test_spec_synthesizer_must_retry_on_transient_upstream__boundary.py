"""Boundary-case tests for bob3.synthesizer transient-upstream retry behavior.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.

These boundary tests verify that the retry logic and synthesizer functions
handle edge cases gracefully without raising exceptions.
"""
import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from bob3.synthesizer import synthesize_for_feature, score_gate_loop, ScoreGateReport


class TestSynthesizeForFeatureBoundary:
    """Boundary cases: minimum/empty inputs must not raise."""

    @pytest.mark.asyncio
    async def test_empty_description_does_not_raise(self):
        """Empty description is boundary: must return None or list, not raise."""
        async def empty_response(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=empty_response):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "1"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="boundary feature",
                        description="",  # empty description - boundary
                    )

        # Must return None (not raise) when LLM returns empty
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_description_does_not_raise(self):
        """Whitespace-only description is boundary: must return None or list, not raise."""
        async def empty_response(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=empty_response):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "1"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="boundary feature",
                        description="   \n\t  ",  # whitespace-only - boundary
                    )

        assert result is None

    @pytest.mark.asyncio
    async def test_max_attempts_one_does_not_hang(self):
        """BOB3_SYNTH_MAX_ATTEMPTS=1 is minimum: exactly one attempt, returns promptly."""
        call_count = 0

        async def always_empty(*, project_id, prompt, workspace=None):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=always_empty):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "1"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="proj-1",
                        title="min attempts feature",
                        description="minimum retry boundary",
                    )

        assert result is None
        assert call_count == 1  # exactly one attempt

    @pytest.mark.asyncio
    async def test_empty_project_context_does_not_raise(self):
        """Empty project_context is boundary: must not raise."""
        async def valid_response(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py"]'

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=valid_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_for_feature(
                    project_id="proj-1",
                    title="empty context feature",
                    description="test with empty project_context",
                    project_context="",  # empty - boundary
                )

        assert result is not None

    @pytest.mark.asyncio
    async def test_none_workspace_does_not_raise(self):
        """workspace=None is boundary: must not raise."""
        async def valid_response(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py"]'

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=valid_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_for_feature(
                    project_id="proj-1",
                    title="none workspace feature",
                    description="test with None workspace",
                    workspace=None,  # explicit None - boundary
                )

        assert result is not None

    @pytest.mark.asyncio
    async def test_score_gate_loop_max_retries_zero_returns_report(self):
        """score_gate_loop with max_retries=0 is boundary: returns report, not raises."""
        async def valid_synthesize(**kwargs):
            return ["File exists: src/foo.py", "pytest: tests/test_foo.py",
                    "pytest: tests/test_foo_boundary.py — boundary",
                    "pytest: tests/test_foo_error.py — error path"]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=valid_synthesize,
                title="zero retries feature",
                description="max_retries=0 boundary",
                project_id="proj-1",
                max_retries=0,
            )

        assert isinstance(report, ScoreGateReport)

    @pytest.mark.asyncio
    async def test_score_gate_loop_with_always_none_synthesize_and_fallback(self):
        """score_gate_loop with synthesize_fn returning None: use_fallback protects caller."""
        async def always_none(**kwargs):
            return None

        with patch("asyncio.sleep", new_callable=AsyncMock):
            report = await score_gate_loop(
                synthesize_fn=always_none,
                title="always none boundary feature",
                description="boundary: synthesize always returns None",
                project_id="proj-1",
                max_retries=1,
                use_fallback=True,
            )

        assert isinstance(report, ScoreGateReport)
        # Should not raise; report may have gate_failed=True with deterministic criteria


class TestRetryBoundaryEdgeCases:
    """Edge cases in retry boundary behavior."""

    @pytest.mark.asyncio
    async def test_single_char_title_does_not_raise(self):
        """Minimum-length title (1 char) is boundary: must not raise."""
        async def empty_response(*, project_id, prompt, workspace=None):
            return ""

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=empty_response):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "1"}):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await synthesize_for_feature(
                        project_id="p",
                        title="x",  # minimum 1 char title - boundary
                        description="short",
                    )

        assert result is None  # None, not raised

    @pytest.mark.asyncio
    async def test_retry_feedback_none_does_not_raise(self):
        """retry_feedback=None is boundary: must not raise."""
        async def valid_response(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py"]'

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=valid_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_for_feature(
                    project_id="proj-1",
                    title="none feedback feature",
                    description="retry_feedback=None boundary",
                    retry_feedback=None,  # explicit None - boundary
                )

        assert result is not None

    @pytest.mark.asyncio
    async def test_retry_feedback_empty_string_does_not_raise(self):
        """retry_feedback="" is boundary: must not raise."""
        async def valid_response(*, project_id, prompt, workspace=None):
            return '["File exists: src/foo.py"]'

        with patch("bob3.spec_synthesizer._llm_spawn_synthesizer", side_effect=valid_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_for_feature(
                    project_id="proj-1",
                    title="empty feedback feature",
                    description="retry_feedback='' boundary",
                    retry_feedback="",  # empty string - boundary (falsy, ignored)
                )

        assert result is not None
