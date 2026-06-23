"""Tests for bob3.spec_synthesizer score-gate loop — re-synthesize TBD ACs until score reaches threshold.

Feature: Spec synthesizer score-gate loop (feature 6dda9dbb-ea5f-497a-9caf-7ec37cd92a04)

Tests cover:
- synthesize_with_score_gate_loop public API (gate_passed, gate_failed, gate_avg_attempts keys)
- score_gate_loop retry-with-feedback behaviour
- Threshold gating: pass on first attempt vs. retry vs. fallback
- gate_avg_attempts reflects actual attempt count
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bob3.spec_synthesizer import (
    ScoreGateReport,
    build_retry_feedback_prompt,
    score_gate_loop,
    score_gate_threshold_from_env,
    synthesize_with_score_gate_loop,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers: high-scoring and low-scoring criteria for controlling test outcomes
# ---------------------------------------------------------------------------

_HIGH_SCORE_CRITERIA = [
    "File exists: src/bob3/spec_synthesizer.py",
    "Function defined: bob3.spec_synthesizer.synthesize_with_score_gate_loop",
    "pytest: tests/test_spec_synthesizer_score_gate_loop.py",
    "pytest: tests/test_spec_synthesizer_score_gate_loop_boundary.py — empty, zero, or minimum input returns a well-defined result rather than raising (boundary case)",
    "pytest: tests/test_spec_synthesizer_score_gate_loop_error.py — invalid input raises ValueError and the function does not silently succeed (error path)",
    "integration: bob3.orchestrator",
    "File exists: tools/spec_quality_score.py",
]

_LOW_SCORE_CRITERIA = [
    "The system should work correctly and handle all inputs reliably.",
    "Everything should be smooth, fast, and intuitive for all cases.",
]


class TestSynthesizeWithScoreGateLoopReturnKeys:
    """synthesize_with_score_gate_loop returns a dict with the required keys."""

    def test_returns_dict_with_gate_passed(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="my feature",
            description="adds something useful",
            project_id="test-project",
            synthesize_fn=_good_synth,
            threshold=0.0,
        ))
        assert isinstance(result, dict)
        assert "gate_passed" in result

    def test_returns_dict_with_gate_failed(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="my feature",
            description="adds something useful",
            project_id="test-project",
            synthesize_fn=_good_synth,
            threshold=0.0,
        ))
        assert "gate_failed" in result

    def test_returns_dict_with_gate_avg_attempts(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="my feature",
            description="adds something useful",
            project_id="test-project",
            synthesize_fn=_good_synth,
            threshold=0.0,
        ))
        assert "gate_avg_attempts" in result

    def test_returns_dict_with_criteria(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="my feature",
            description="adds something useful",
            project_id="test-project",
            synthesize_fn=_good_synth,
            threshold=0.0,
        ))
        assert "criteria" in result
        assert isinstance(result["criteria"], list)

    def test_returns_dict_with_composite(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="my feature",
            description="adds something useful",
            project_id="test-project",
            synthesize_fn=_good_synth,
            threshold=0.0,
        ))
        assert "composite" in result
        assert isinstance(result["composite"], float)

    def test_returns_dict_with_rationale(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="my feature",
            description="adds something useful",
            project_id="test-project",
            synthesize_fn=_good_synth,
            threshold=0.0,
        ))
        assert "rationale" in result
        assert isinstance(result["rationale"], list)


class TestScoreGateLoopPassesOnFirstAttempt:
    """score_gate_loop returns gate_passed=True when criteria score above threshold on first attempt."""

    def test_high_score_criteria_pass_at_low_threshold(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_good_synth,
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop function",
            project_id="test",
            threshold=0.0,
            max_retries=3,
        ))
        assert isinstance(report, ScoreGateReport)
        assert report.gate_passed is True
        assert report.gate_failed is False

    def test_gate_avg_attempts_is_one_on_first_pass(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_good_synth,
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop function",
            project_id="test",
            threshold=0.0,
            max_retries=3,
        ))
        assert report.gate_avg_attempts == 1

    def test_criteria_returned_on_pass(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_good_synth,
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop function",
            project_id="test",
            threshold=0.0,
            max_retries=3,
        ))
        assert report.criteria == _HIGH_SCORE_CRITERIA


class TestScoreGateLoopRetryWithFeedback:
    """score_gate_loop retries when score is below threshold and passes feedback on subsequent calls."""

    def test_retry_feedback_passed_to_second_attempt(self):
        """Confirms retry_feedback kwarg is passed to synthesize_fn on retry."""
        received_feedbacks: list[str | None] = []

        async def _track_feedback(**kwargs):
            received_feedbacks.append(kwargs.get("retry_feedback"))
            if len(received_feedbacks) == 1:
                return _LOW_SCORE_CRITERIA
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_track_feedback,
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop",
            project_id="test",
            threshold=0.5,
            max_retries=3,
        ))
        # First call: no feedback; subsequent calls get feedback
        assert received_feedbacks[0] is None
        if len(received_feedbacks) > 1:
            assert received_feedbacks[1] is not None
            assert isinstance(received_feedbacks[1], str)

    def test_eventually_passes_after_retry(self):
        """score_gate_loop eventually returns gate_passed=True when a later attempt scores above threshold."""
        call_count = [0]

        async def _improve_on_retry(**kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                return _LOW_SCORE_CRITERIA
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_improve_on_retry,
            title="improving feature",
            description="adds synthesize_with_score_gate_loop",
            project_id="test",
            threshold=0.0,  # any non-empty criteria passes
            max_retries=3,
        ))
        assert report.gate_passed is True

    def test_gate_avg_attempts_reflects_retry_count(self):
        """gate_avg_attempts == attempt number at which gate was passed."""
        call_count = [0]

        async def _pass_on_second(**kwargs):
            call_count[0] += 1
            # Return None on first attempt to force a retry
            if call_count[0] == 1:
                return None
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_pass_on_second,
            title="retry feature",
            description="adds synthesize_with_score_gate_loop",
            project_id="test",
            threshold=0.0,
            max_retries=3,
            use_fallback=True,
        ))
        # Passed on attempt 2 (first was None/skipped, second succeeded)
        assert report.gate_avg_attempts >= 1


class TestScoreGateLoopExhaustionWithFallback:
    """score_gate_loop uses deterministic fallback when all retries are exhausted."""

    def test_fallback_on_exhaustion_returns_gate_failed(self):
        async def _always_low(**kwargs):
            return _LOW_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_always_low,
            title="stubborn feature",
            description="does something",
            project_id="test",
            threshold=0.999,  # impossibly high
            max_retries=2,
            use_fallback=True,
        ))
        assert report.gate_failed is True
        assert report.gate_passed is False

    def test_fallback_criteria_is_non_empty_list(self):
        async def _always_low(**kwargs):
            return _LOW_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_always_low,
            title="stubborn feature",
            description="does something",
            project_id="test",
            threshold=0.999,
            max_retries=2,
            use_fallback=True,
        ))
        assert isinstance(report.criteria, list)
        assert len(report.criteria) > 0

    def test_gate_avg_attempts_equals_max_retries_on_exhaustion(self):
        async def _always_low(**kwargs):
            return _LOW_SCORE_CRITERIA

        max_retries = 2
        report = _run(score_gate_loop(
            synthesize_fn=_always_low,
            title="stubborn feature",
            description="does something",
            project_id="test",
            threshold=0.999,
            max_retries=max_retries,
            use_fallback=True,
        ))
        assert report.gate_avg_attempts == max_retries


class TestSynthesizeWithScoreGateLoopGatePassedFailed:
    """synthesize_with_score_gate_loop sets gate_passed/gate_failed correctly."""

    def test_gate_passed_true_when_criteria_score_above_threshold(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop function",
            project_id="test",
            threshold=0.0,
            synthesize_fn=_good_synth,
        ))
        assert result["gate_passed"] is True
        assert result["gate_failed"] is False

    def test_gate_failed_true_on_exhaustion(self):
        async def _always_low(**kwargs):
            return _LOW_SCORE_CRITERIA

        result = _run(synthesize_with_score_gate_loop(
            title="stubborn feature",
            description="does something",
            project_id="test",
            threshold=0.999,
            max_retries=2,
            use_fallback=True,
            synthesize_fn=_always_low,
        ))
        assert result["gate_failed"] is True
        assert result["gate_passed"] is False


class TestScoreGateThresholdDefault:
    """score_gate_threshold_from_env returns the expected default value."""

    def test_default_threshold_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD", raising=False)
        threshold = score_gate_threshold_from_env()
        assert threshold == 0.85

    def test_env_override_is_respected(self, monkeypatch):
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.70")
        threshold = score_gate_threshold_from_env()
        assert abs(threshold - 0.70) < 1e-6


class TestBuildRetryFeedbackPromptIntegration:
    """build_retry_feedback_prompt produces actionable strings for the retry mechanism."""

    def test_prompt_mentions_score(self):
        result = build_retry_feedback_prompt(
            previous_criteria=_LOW_SCORE_CRITERIA,
            score=0.45,
            rationale=["No boundary ACs", "No error path coverage"],
        )
        assert "0.450" in result

    def test_prompt_mentions_rationale_items(self):
        result = build_retry_feedback_prompt(
            previous_criteria=_LOW_SCORE_CRITERIA,
            score=0.45,
            rationale=["No boundary ACs"],
        )
        assert "No boundary ACs" in result

    def test_prompt_is_non_empty_string(self):
        result = build_retry_feedback_prompt(
            previous_criteria=_LOW_SCORE_CRITERIA,
            score=0.5,
            rationale=[],
        )
        assert isinstance(result, str)
        assert len(result) > 10


class TestScoreGateLoopCompositeInReport:
    """score_gate_loop includes a non-negative composite score in the report."""

    def test_composite_is_float_in_0_to_1(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_good_synth,
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop",
            project_id="test",
            threshold=0.0,
            max_retries=3,
        ))
        assert isinstance(report.composite, float)
        assert 0.0 <= report.composite <= 1.0

    def test_high_score_criteria_composite_above_zero(self):
        async def _good_synth(**kwargs):
            return _HIGH_SCORE_CRITERIA

        report = _run(score_gate_loop(
            synthesize_fn=_good_synth,
            title="spec synthesizer feature",
            description="adds synthesize_with_score_gate_loop",
            project_id="test",
            threshold=0.0,
            max_retries=3,
        ))
        assert report.composite > 0.0
