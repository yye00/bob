"""Error-path tests for bob3.spec_synthesizer score-gate loop.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (error path).

Feature: Spec synthesizer score-gate loop — re-synthesize TBD ACs until
score reaches threshold.
"""
from __future__ import annotations

import asyncio

import pytest

from bob3.spec_synthesizer import (
    deterministic_fallback,
    score_gate_loop,
    synthesize_with_score_gate,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSynthesizeWithScoreGateInvalidTitle:
    """synthesize_with_score_gate raises ValueError for invalid (empty) title."""

    def test_empty_title_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty title"):
            _run(synthesize_with_score_gate(
                title="",
                description="some description",
                project_id="test",
            ))

    def test_whitespace_only_title_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty title"):
            _run(synthesize_with_score_gate(
                title="   ",
                description="some description",
                project_id="test",
            ))

    def test_none_title_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            _run(synthesize_with_score_gate(
                title=None,  # type: ignore[arg-type]
                description="some description",
                project_id="test",
            ))


class TestScoreGateLoopNoFallbackRaisesOnExhaustion:
    """score_gate_loop raises ValueError when use_fallback=False and all attempts fail."""

    def test_all_none_no_fallback_raises(self):
        """When synthesize_fn always returns None and use_fallback=False, raises ValueError."""
        async def _always_none(**kwargs):
            return None

        with pytest.raises(ValueError, match="score_gate_loop"):
            _run(score_gate_loop(
                synthesize_fn=_always_none,
                title="test feature",
                description="does something",
                project_id="test",
                max_retries=2,
                use_fallback=False,
            ))

    def test_all_empty_no_fallback_raises(self):
        """When synthesize_fn always returns empty list and use_fallback=False, raises ValueError."""
        async def _always_empty(**kwargs):
            return []

        with pytest.raises(ValueError, match="score_gate_loop"):
            _run(score_gate_loop(
                synthesize_fn=_always_empty,
                title="empty result feature",
                description="does something",
                project_id="test",
                max_retries=1,
                use_fallback=False,
            ))

    def test_does_not_silently_succeed_when_raising(self):
        """Confirms ValueError is raised, not a successful ScoreGateReport returned."""
        async def _always_none(**kwargs):
            return None

        result = None
        raised = False
        try:
            result = _run(score_gate_loop(
                synthesize_fn=_always_none,
                title="test feature",
                description="does something",
                project_id="test",
                max_retries=1,
                use_fallback=False,
            ))
        except ValueError:
            raised = True

        assert raised is True, "Expected ValueError to be raised but was not"
        assert result is None, "Expected no result to be returned on error"


class TestDeterministicFallbackInvalidTitle:
    """deterministic_fallback raises ValueError for degenerate (all stop-words) titles."""

    def test_all_stopwords_title_raises(self):
        """A title that resolves to only stop-words raises ValueError."""
        with pytest.raises(ValueError, match="Cannot synthesize"):
            deterministic_fallback("the a an")

    def test_empty_title_raises(self):
        """An empty title string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot synthesize"):
            deterministic_fallback("")

    def test_whitespace_only_title_raises(self):
        """A whitespace-only title raises ValueError."""
        with pytest.raises(ValueError, match="Cannot synthesize"):
            deterministic_fallback("   ")

    def test_does_not_silently_return_on_bad_title(self):
        """Confirms ValueError propagates rather than silently returning criteria."""
        result = None
        raised = False
        try:
            result = deterministic_fallback("")
        except ValueError:
            raised = True

        assert raised is True, "Expected ValueError, but no exception was raised"
        assert result is None, "Expected no result to be returned on degenerate title"
