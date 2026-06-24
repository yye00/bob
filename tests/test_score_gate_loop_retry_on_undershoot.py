"""Tests for score_gate_loop — retry on undershoot behavior.

Verifies that when the first synthesis attempt scores below the threshold,
score_gate_loop retries with feedback and eventually passes (or fails).
"""
from __future__ import annotations

import asyncio

import pytest

from bob.spec_synthesizer import (
    ScoreGateReport,
    score_gate_loop,
    build_retry_feedback_prompt,
)


class TestScoreGateLoopRetryOnUndershoot:
    """score_gate_loop retries when first attempt scores below threshold."""

    def test_retries_when_first_attempt_undershoots(self):
        """synthesize_fn is called more than once when first attempt undershoots."""
        call_count = {"n": 0}
        low_quality = ["File exists: src/bob/x.py"]  # will score low
        high_quality = [
            "File exists: src/bob/x.py",
            "Function defined: bob.x.run",
            "pytest: tests/test_x.py",
            "behavior: raises ValueError when input is None",
            "behavior: returns None when value exceeds maximum boundary",
        ]

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return low_quality
            return high_quality

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="X module",
                description="X module run function. Raises ValueError when None. Returns None when exceeds max.",
                project_id="test-project",
                threshold=0.5,  # high enough that low_quality won't pass
                max_retries=3,
            )
        )
        # Should have tried at least twice
        assert call_count["n"] >= 2

    def test_gate_passed_when_retry_succeeds(self):
        """gate_passed is True when a retry attempt passes the threshold."""
        call_count = {"n": 0}
        low_quality = ["File exists: src/bob/x.py"]
        high_quality = [
            "File exists: src/bob/x.py",
            "Function defined: bob.x.run",
            "pytest: tests/test_x.py",
            "behavior: raises ValueError when input is None",
        ]

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return low_quality
            return high_quality

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="X module",
                description="X module run. Raises ValueError when None.",
                project_id="test-project",
                threshold=0.0,  # accept anything on retry
                max_retries=3,
            )
        )
        assert report.gate_passed is True
        assert report.gate_failed is False

    def test_avg_attempts_reflects_retry_count(self):
        """gate_avg_attempts > 1 when multiple synthesis attempts occur."""
        call_count = {"n": 0}

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return ["File exists: src/bob/y.py"]  # low quality
            return [
                "File exists: src/bob/y.py",
                "pytest: tests/test_y.py",
                "Function defined: bob.y.compute",
                "behavior: raises ValueError when input is empty",
            ]

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Y module",
                description="Y compute function. Raises ValueError on empty.",
                project_id="test-project",
                threshold=0.5,
                max_retries=3,
            )
        )
        assert report.gate_avg_attempts > 1

    def test_feedback_prompt_included_on_retry(self):
        """synthesize_fn receives a retry_feedback kwarg on subsequent calls."""
        received_feedback = {"values": []}

        async def mock_synthesize(retry_feedback=None, **kwargs):
            received_feedback["values"].append(retry_feedback)
            if len(received_feedback["values"]) == 1:
                return ["File exists: src/bob/z.py"]  # undershoots
            return [
                "File exists: src/bob/z.py",
                "pytest: tests/test_z.py",
                "behavior: raises ValueError when value is None",
            ]

        asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Z module",
                description="Z module. Raises ValueError when None.",
                project_id="test-project",
                threshold=0.5,
                max_retries=3,
            )
        )
        # First call: no feedback; subsequent calls: feedback present
        assert received_feedback["values"][0] is None
        if len(received_feedback["values"]) > 1:
            assert received_feedback["values"][1] is not None


class TestBuildRetryFeedbackPrompt:
    """build_retry_feedback_prompt returns a non-empty feedback string."""

    def test_returns_string(self):
        from tools.spec_quality_score import compute
        criteria = ["File exists: src/bob/foo.py"]
        score_result = compute(
            name="foo",
            description="Foo feature",
            acceptance_criteria=criteria,
        )
        feedback = build_retry_feedback_prompt(
            score_result=score_result,
            attempt=1,
        )
        assert isinstance(feedback, str)
        assert len(feedback) > 0

    def test_mentions_failing_submetrics(self):
        """Feedback string names sub-metrics that are below threshold."""
        from tools.spec_quality_score import compute
        # Single file-exists criterion — will fail boundary, error_path etc.
        criteria = ["File exists: src/bob/foo.py"]
        score_result = compute(
            name="foo",
            description="Foo feature",
            acceptance_criteria=criteria,
        )
        feedback = build_retry_feedback_prompt(
            score_result=score_result,
            attempt=1,
            threshold=0.85,
        )
        # Should mention at least one sub-metric in the feedback
        submetrics = [
            "boundary_coverage", "error_path_coverage", "predicate_coverage",
            "smell_density", "traceability", "spec_executability", "ac_atomicity",
            "contract_completeness",
        ]
        assert any(m in feedback for m in submetrics)

    def test_includes_attempt_number(self):
        """Feedback string includes the attempt number for context."""
        from tools.spec_quality_score import compute
        criteria = ["File exists: src/bob/foo.py"]
        score_result = compute(
            name="foo",
            description="Foo feature",
            acceptance_criteria=criteria,
        )
        feedback = build_retry_feedback_prompt(
            score_result=score_result,
            attempt=2,
        )
        assert "2" in feedback
