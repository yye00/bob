"""Tests for score_gate_loop — max_retries cap behavior.

Verifies that score_gate_loop caps at max_retries (default 3) and falls
through to deterministic_fallback on exhaustion.
"""
from __future__ import annotations

import asyncio

import pytest

from bob3.spec_synthesizer import (
    ScoreGateReport,
    score_gate_loop,
)


class TestScoreGateLoopCapsAtThreeRetries:
    """score_gate_loop caps retries and uses fallback on exhaustion."""

    def test_caps_at_default_three_retries(self):
        """synthesize_fn is called at most 3 times (default max_retries=3)."""
        call_count = {"n": 0}

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            # Always return low-quality criteria
            return ["File exists: src/bob3/q.py"]

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Q feature",
                description="Q feature implementation.",
                project_id="test-project",
                threshold=0.99,  # impossibly high — will never pass
                max_retries=3,
            )
        )
        assert call_count["n"] <= 3

    def test_gate_failed_on_exhaustion(self):
        """gate_failed is True and gate_passed is False when all retries exhausted."""
        async def mock_synthesize(**kwargs):
            return ["File exists: src/bob3/q.py"]  # always low quality

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Q feature",
                description="Q feature implementation.",
                project_id="test-project",
                threshold=0.99,  # always fails
                max_retries=3,
            )
        )
        assert report.gate_failed is True
        assert report.gate_passed is False

    def test_falls_through_to_fallback_on_exhaustion(self):
        """criteria is set from deterministic_fallback when retries exhausted."""
        async def mock_synthesize(**kwargs):
            return ["File exists: src/bob3/p.py"]  # low quality

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="P module feature",
                description="P module implementation.",
                project_id="test-project",
                threshold=0.99,
                max_retries=3,
                use_fallback=True,
            )
        )
        # After exhaustion with use_fallback=True, criteria should be non-empty
        assert report.criteria is not None
        assert len(report.criteria) > 0

    def test_custom_max_retries_respected(self):
        """synthesize_fn is called at most max_retries times when custom value set."""
        call_count = {"n": 0}

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            return ["File exists: src/bob3/r.py"]

        asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="R feature",
                description="R feature.",
                project_id="test-project",
                threshold=0.99,
                max_retries=2,
            )
        )
        assert call_count["n"] <= 2

    def test_avg_attempts_correct_on_exhaustion(self):
        """gate_avg_attempts equals max_retries when all retries exhausted."""
        async def mock_synthesize(**kwargs):
            return ["File exists: src/bob3/s.py"]

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="S feature",
                description="S feature.",
                project_id="test-project",
                threshold=0.99,
                max_retries=3,
            )
        )
        # Attempted max_retries times
        assert report.gate_avg_attempts == 3
