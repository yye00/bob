"""Tests for score_gate_loop — malformed synthesizer response behavior.

Verifies that score_gate_loop raises ValueError when synthesizer returns
invalid empty output after all retries, and that sanitize_spec_file does
not increment the counter when synthesis fails with an exception.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import yaml

from bob3.spec_synthesizer import (
    ScoreGateReport,
    score_gate_loop,
    sanitize_spec_file,
)


class TestScoreGateLoopRaisesOnInvalidAfterRetries:
    """score_gate_loop raises ValueError when synthesizer always returns invalid output."""

    def test_raises_value_error_when_all_retries_return_none(self):
        """ValueError raised when synthesizer returns None after all retries."""
        async def mock_synthesize(**kwargs):
            return None  # always invalid

        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                score_gate_loop(
                    synthesize_fn=mock_synthesize,
                    title="Broken feature",
                    description="Feature with broken synthesizer.",
                    project_id="test-project",
                    threshold=0.85,
                    max_retries=3,
                    use_fallback=False,  # no fallback — must raise
                )
            )

    def test_raises_value_error_when_all_retries_return_empty(self):
        """ValueError raised when synthesizer returns empty list after all retries."""
        async def mock_synthesize(**kwargs):
            return []  # always empty

        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                score_gate_loop(
                    synthesize_fn=mock_synthesize,
                    title="Broken feature",
                    description="Feature with empty synthesizer.",
                    project_id="test-project",
                    threshold=0.85,
                    max_retries=3,
                    use_fallback=False,
                )
            )


class TestSanitizeSpecFileExceptionHandling:
    """sanitize_spec_file does not increment counter when synthesis throws."""

    def test_synthesized_count_not_incremented_on_exception(self, tmp_path):
        """report['synthesized'] stays 0 when synthesize_for_feature raises."""
        spec = {
            "features": [
                {
                    "title": "Broken feature",
                    "description": "A feature with a broken synthesizer.",
                    "acceptance_criteria": "TBD: synthesize",
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.safe_dump(spec))

        async def failing_synthesize(**kwargs):
            raise RuntimeError("Synthesizer exploded")

        with patch("bob3.spec_synthesizer.synthesize_for_feature", side_effect=RuntimeError("boom")):
            report = asyncio.get_event_loop().run_until_complete(
                sanitize_spec_file(
                    spec_file,
                    project_id="test-project",
                    dry_run=True,
                    use_fallback=False,
                )
            )
        # synthesized count must not be incremented when synthesis fails with exception
        assert report["synthesized"] == 0

    def test_fell_back_count_not_incremented_on_exception(self, tmp_path):
        """report['fell_back'] stays 0 when synthesize_for_feature raises and fallback disabled."""
        spec = {
            "features": [
                {
                    "title": "Exception feature",
                    "description": "Feature whose synthesizer always throws.",
                    "acceptance_criteria": "TBD",
                }
            ]
        }
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.safe_dump(spec))

        with patch("bob3.spec_synthesizer.synthesize_for_feature", side_effect=RuntimeError("boom")):
            report = asyncio.get_event_loop().run_until_complete(
                sanitize_spec_file(
                    spec_file,
                    project_id="test-project",
                    dry_run=True,
                    use_fallback=False,
                )
            )
        assert report["fell_back"] == 0
