"""Boundary tests for bob.spec_synthesizer score-gate loop.

Verifies that empty, zero, or minimum inputs to score-gate loop functions
return well-defined results rather than raising unexpected exceptions.

Feature: Spec synthesizer score-gate loop — re-synthesize TBD ACs until
score reaches threshold.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from bob.spec_synthesizer import (
    ScoreGateReport,
    build_retry_feedback_prompt,
    deterministic_fallback,
    is_placeholder,
    parse_criteria_response,
    score_gate_loop,
    score_gate_threshold_from_env,
    score_synthesized_acs,
    synthesize_with_score_gate,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestScoreGateLoopEmptyDescription:
    """score_gate_loop with empty/minimal description returns a ScoreGateReport, not raises."""

    def test_empty_description_returns_gate_report(self):
        """Empty description string produces a fallback report, not an exception."""
        async def _fast_synth(**kwargs):
            return None  # trigger fallback immediately

        report = _run(score_gate_loop(
            synthesize_fn=_fast_synth,
            title="my feature",
            description="",
            project_id="test",
            max_retries=1,
            use_fallback=True,
        ))
        from bob.spec_synthesizer import ScoreGateReport as _SGR
        assert isinstance(report, _SGR)
        assert report.criteria is not None
        assert isinstance(report.criteria, list)

    def test_whitespace_only_description_returns_gate_report(self):
        """Whitespace-only description does not raise."""
        async def _fast_synth(**kwargs):
            return None

        report = _run(score_gate_loop(
            synthesize_fn=_fast_synth,
            title="my feature",
            description="   ",
            project_id="test",
            max_retries=1,
            use_fallback=True,
        ))
        from bob.spec_synthesizer import ScoreGateReport as _SGR
        assert isinstance(report, _SGR)
        assert report.criteria is not None

    def test_max_retries_zero_not_accepted_but_one_is_minimum(self):
        """max_retries=1 (minimum) terminates after one attempt and returns a report."""
        async def _always_none(**kwargs):
            return None

        report = _run(score_gate_loop(
            synthesize_fn=_always_none,
            title="minimal feature",
            description="does something",
            project_id="test",
            max_retries=1,
            use_fallback=True,
        ))
        from bob.spec_synthesizer import ScoreGateReport as _SGR
        assert isinstance(report, _SGR)
        assert report.gate_failed is True
        assert report.gate_avg_attempts == 1


class TestScoreGateLoopZeroThreshold:
    """score_gate_loop with threshold=0.0 always passes on first valid attempt."""

    def test_threshold_zero_passes_any_non_empty_criteria(self):
        """Any non-empty synthesized criteria pass when threshold=0.0."""
        minimal_criteria = [
            "File exists: src/bob/foo.py",
        ]

        async def _minimal_synth(**kwargs):
            return minimal_criteria

        report = _run(score_gate_loop(
            synthesize_fn=_minimal_synth,
            title="foo feature",
            description="adds foo",
            project_id="test",
            threshold=0.0,
            max_retries=3,
            use_fallback=False,
        ))
        from bob.spec_synthesizer import ScoreGateReport as _SGR
        assert isinstance(report, _SGR)
        assert report.gate_passed is True
        assert report.gate_avg_attempts == 1


class TestScoreGateLoopMinimumInput:
    """score_gate_loop with minimal valid input returns a well-defined ScoreGateReport."""

    def test_single_char_title_with_fallback(self):
        """Single-character title produces fallback criteria without raising."""
        async def _always_none(**kwargs):
            return None

        # Single char after stop-word stripping might produce a valid slug
        report = _run(score_gate_loop(
            synthesize_fn=_always_none,
            title="x feature",
            description="",
            project_id="test",
            max_retries=1,
            use_fallback=True,
        ))
        from bob.spec_synthesizer import ScoreGateReport as _SGR
        assert isinstance(report, _SGR)
        assert report.criteria is not None

    def test_report_has_required_fields(self):
        """ScoreGateReport from a boundary call has all required fields."""
        async def _always_none(**kwargs):
            return None

        report = _run(score_gate_loop(
            synthesize_fn=_always_none,
            title="minimal boundary feature",
            description="",
            project_id="test",
            max_retries=1,
            use_fallback=True,
        ))
        assert hasattr(report, "gate_passed")
        assert hasattr(report, "gate_failed")
        assert hasattr(report, "gate_avg_attempts")
        assert hasattr(report, "criteria")
        assert hasattr(report, "composite")
        assert hasattr(report, "rationale")


class TestScoreSynthesizedAcsEmptyInput:
    """score_synthesized_acs with empty/zero inputs returns 0.0, not raises."""

    def test_empty_criteria_returns_zero(self):
        result = score_synthesized_acs([], name="test", description="")
        assert result == 0.0

    def test_empty_list_with_none_description_returns_zero(self):
        result = score_synthesized_acs([], name="test", description=None)
        assert result == 0.0


class TestBuildRetryFeedbackPromptBoundary:
    """build_retry_feedback_prompt handles minimum/empty inputs without raising."""

    def test_empty_rationale_produces_string(self):
        result = build_retry_feedback_prompt(
            previous_criteria=[],
            score=0.5,
            rationale=[],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_zero_score_produces_string(self):
        result = build_retry_feedback_prompt(
            previous_criteria=["File exists: src/foo.py"],
            score=0.0,
            rationale=["No boundary ACs"],
        )
        assert isinstance(result, str)
        assert "0.000" in result

    def test_attempt_one_produces_string(self):
        result = build_retry_feedback_prompt(
            previous_criteria=[],
            score=0.4,
            rationale=[],
            attempt=1,
        )
        assert isinstance(result, str)
        assert "Attempt 1" in result


class TestIsPlaceholderBoundary:
    """is_placeholder with empty/minimal input returns True, not raises."""

    def test_none_returns_true(self):
        assert is_placeholder(None) is True

    def test_empty_string_returns_true(self):
        assert is_placeholder("") is True

    def test_empty_list_returns_true(self):
        assert is_placeholder([]) is True

    def test_whitespace_string_returns_true(self):
        assert is_placeholder("   ") is True


class TestParseCriteriaResponseBoundary:
    """parse_criteria_response with empty/minimum input returns None, not raises."""

    def test_empty_string_returns_none(self):
        assert parse_criteria_response("") is None

    def test_whitespace_returns_none(self):
        assert parse_criteria_response("   ") is None

    def test_no_json_block_returns_none(self):
        assert parse_criteria_response("This is just prose.") is None


class TestScoreGateThresholdFromEnvBoundary:
    """score_gate_threshold_from_env returns 0.85 default with empty/invalid env."""

    def test_unset_env_returns_default(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        assert score_gate_threshold_from_env() == 0.85

    def test_zero_threshold_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        assert score_gate_threshold_from_env() == 0.0


class TestSynthesizeWithScoreGateBoundary:
    """synthesize_with_score_gate boundary: empty description uses fallback, not raises."""

    def test_empty_description_with_fallback_returns_report(self, monkeypatch):
        """Empty description triggers fallback on None synthesis, not exception."""
        async def _always_none(**kwargs):
            return None

        monkeypatch.setattr(
            "bob.spec_synthesizer.synthesize_for_feature", _always_none
        )

        report = _run(synthesize_with_score_gate(
            title="some feature",
            description="",
            project_id="test",
            max_retries=1,
            use_fallback=True,
        ))
        assert isinstance(report, ScoreGateReport)
        assert report.criteria is not None
