"""Tests for score_gate_loop — boundary: threshold at 0.85.

Verifies that score_gate_loop accepts criteria when composite exactly equals
the threshold minimum value of 0.85.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from bob3.spec_synthesizer import (
    ScoreGateReport,
    score_gate_loop,
)


class TestScoreGateLoopBoundaryThreshold:
    """score_gate_loop accepts when composite == threshold (boundary minimum)."""

    def test_accepts_when_composite_equals_threshold(self):
        """gate_passed is True when synthesized ACs score exactly at threshold."""
        # We patch the scorer to return exactly 0.85
        criteria = [
            "File exists: src/bob3/boundary.py",
            "Function defined: bob3.boundary.check",
            "pytest: tests/test_boundary.py",
            "behavior: raises ValueError when input exceeds maximum boundary",
            "behavior: returns None when value is below minimum boundary",
        ]

        async def mock_synthesize(**kwargs):
            return criteria

        from tools.spec_quality_score import CompositeScore

        mock_score = CompositeScore(
            smell_density=1.0,
            predicate_coverage=1.0,
            contract_completeness=1.0,
            boundary_coverage=1.0,
            error_path_coverage=1.0,
            traceability=1.0,
            spec_executability=1.0,
            ac_atomicity=1.0,
            composite=0.85,
        )

        with patch("bob3.spec_synthesizer.score_synthesized_acs", return_value=0.85):
            report = asyncio.get_event_loop().run_until_complete(
                score_gate_loop(
                    synthesize_fn=mock_synthesize,
                    title="Boundary check",
                    description="Check boundaries. Raises ValueError on max. Returns None on min.",
                    project_id="test-project",
                    threshold=0.85,
                )
            )
        assert report.gate_passed is True
        assert report.gate_failed is False

    def test_rejects_when_composite_just_below_threshold(self):
        """gate_failed is True when composite is just below threshold."""
        async def mock_synthesize(**kwargs):
            return ["File exists: src/bob3/near.py"]

        with patch("bob3.spec_synthesizer.score_synthesized_acs", return_value=0.8499):
            report = asyncio.get_event_loop().run_until_complete(
                score_gate_loop(
                    synthesize_fn=mock_synthesize,
                    title="Near miss feature",
                    description="Near miss implementation.",
                    project_id="test-project",
                    threshold=0.85,
                    max_retries=1,
                )
            )
        assert report.gate_failed is True


class TestScoreGateLoopEmptyCriteriaList:
    """score_gate_loop handles empty criteria list from synthesizer."""

    def test_does_not_accept_empty_criteria(self):
        """Empty criteria list is treated as failed synthesis."""
        call_count = {"n": 0}

        async def mock_synthesize(**kwargs):
            call_count["n"] += 1
            return []  # empty = synthesis failure

        report = asyncio.get_event_loop().run_until_complete(
            score_gate_loop(
                synthesize_fn=mock_synthesize,
                title="Empty result feature",
                description="Feature whose synthesizer returns empty.",
                project_id="test-project",
                threshold=0.85,
                max_retries=3,
            )
        )
        # Empty list from synthesizer should not be accepted as passing
        assert report.gate_failed is True or report.gate_passed is False
