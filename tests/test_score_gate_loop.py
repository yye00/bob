"""Tests for score_gate_loop — basic happy path and report structure.

Verifies that score_gate_loop accepts criteria that meet or exceed the
threshold and returns a ScoreGateReport with the correct fields.
"""
from __future__ import annotations

import pytest

from bob.spec_synthesizer import (
    ScoreGateReport,
    score_gate_loop,
    score_gate_threshold_from_env,
    score_synthesized_acs,
)


class TestScoreGateLoopHappyPath:
    """score_gate_loop accepts high-quality criteria on the first attempt."""

    def test_returns_score_gate_report(self, monkeypatch):
        """score_gate_loop returns a ScoreGateReport instance."""
        high_quality = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "pytest: tests/test_foo.py",
            "behavior: raises ValueError when input is empty",
            "behavior: returns None when threshold is exceeded",
        ]
        # Synthesizer always returns high-quality criteria
        call_count = {"n": 0}

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            return high_quality

        import asyncio
        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Foo bar feature",
                description="Implement foo.bar that validates inputs and raises ValueError when empty.",
                project_id="test-project",
                threshold=0.0,  # low threshold so first attempt passes
            )
        )
        assert isinstance(report, ScoreGateReport)

    def test_report_has_required_fields(self, monkeypatch):
        """ScoreGateReport has gate_passed, gate_failed, gate_avg_attempts, criteria, composite."""
        high_quality = [
            "File exists: src/bob/mymod.py",
            "Function defined: bob.mymod.run",
            "pytest: tests/test_mymod.py",
            "behavior: raises ValueError when called with empty list",
        ]

        async def mock_synthesize(**kwargs):
            return high_quality

        import asyncio
        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="My module",
                description="My module run function that raises ValueError on empty list.",
                project_id="test-project",
                threshold=0.0,
            )
        )
        assert hasattr(report, "gate_passed")
        assert hasattr(report, "gate_failed")
        assert hasattr(report, "gate_avg_attempts")
        assert hasattr(report, "criteria")
        assert hasattr(report, "composite")

    def test_gate_passed_true_when_first_attempt_passes(self):
        """gate_passed is True and gate_failed is False when first attempt passes."""
        criteria = [
            "File exists: src/bob/widget.py",
            "Function defined: bob.widget.create",
            "pytest: tests/test_widget.py",
            "behavior: raises ValueError when name is empty string",
            "behavior: returns None when limit exceeds maximum boundary",
        ]

        async def mock_synthesize(**kwargs):
            return criteria

        import asyncio
        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Widget creator",
                description="Create widgets. Raises ValueError on empty. Returns None when exceeds max.",
                project_id="test-project",
                threshold=0.0,
            )
        )
        assert report.gate_passed is True
        assert report.gate_failed is False

    def test_attempts_is_one_when_first_pass_succeeds(self):
        """gate_avg_attempts is 1 when criteria pass on the first synthesis."""
        criteria = [
            "File exists: src/bob/alpha.py",
            "pytest: tests/test_alpha.py",
        ]

        async def mock_synthesize(**kwargs):
            return criteria

        import asyncio
        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Alpha module",
                description="Alpha module implementation.",
                project_id="test-project",
                threshold=0.0,
            )
        )
        assert report.gate_avg_attempts == 1


class TestScoreSynthesizedAcs:
    """score_synthesized_acs returns a float composite score."""

    def test_returns_float(self):
        criteria = [
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py",
        ]
        score = score_synthesized_acs(
            criteria=criteria,
            name="foo",
            description="Foo feature.",
        )
        assert isinstance(score, float)

    def test_empty_criteria_scores_zero(self):
        score = score_synthesized_acs(
            criteria=[],
            name="empty",
            description="Empty feature.",
        )
        assert score == 0.0

    def test_high_quality_criteria_scores_above_zero(self):
        criteria = [
            "File exists: src/bob/payment.py",
            "Function defined: bob.payment.process",
            "pytest: tests/test_payment.py",
            "behavior: raises ValueError when amount is negative",
        ]
        score = score_synthesized_acs(
            criteria=criteria,
            name="payment",
            description="Process payment. Raises ValueError when amount is negative.",
        )
        assert score > 0.0
