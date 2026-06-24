"""Integration tests: spec quality gate blocks status='ready' when score < 0.85.

These tests verify that the gate_for_ready function is correctly integrated so
that features with low spec_quality_score cannot be promoted to 'ready'. The
tests use a thin integration layer that mirrors how run_loop.py would call the gate.
"""

from __future__ import annotations

import json

import pytest

from bob.spec_quality.quality_score import compute_score, gate_for_ready


@pytest.fixture(autouse=True)
def _reset_threshold_to_default(monkeypatch):
    """Ensure the quality threshold is 0.85 for every test in this module."""
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
    import bob.spec_quality.threshold_resolver as _tr
    _tr._frozen_value = None
    _tr._frozen_initialized = False
    yield
    _tr._frozen_value = None
    _tr._frozen_initialized = False


THRESHOLD = 0.85


def _simulate_planning_gate(name: str, description: str, criteria: list[str]) -> tuple[bool, str | None]:
    """Simulate the gate check that run_loop performs before promoting to 'ready'."""
    report = compute_score(
        name=name,
        description=description,
        acceptance_criteria=criteria,
    )
    allowed, message = gate_for_ready(report)
    return allowed, message


class TestSpecQualityGateBlocksReady:
    def test_well_specified_feature_passes_gate(self):
        allowed, msg = _simulate_planning_gate(
            name="Compute spec quality score",
            description="Expose compute_score and gate_for_ready in bob.spec_quality.quality_score.",
            criteria=[
                "File exists: src/bob/spec_quality/quality_score.py",
                "Function defined: bob.spec_quality.quality_score.compute_score",
                "Function defined: bob.spec_quality.quality_score.gate_for_ready",
                "pytest: tests/test_quality_score.py",
                "pytest: tests/test_quality_score_gate_blocks_ready.py",
            ],
        )
        assert allowed is True
        assert msg is None or msg == ""

    def test_vague_feature_is_blocked(self):
        allowed, msg = _simulate_planning_gate(
            name="Do stuff",
            description="Make it work",
            criteria=[
                "The system works correctly",
                "It handles all cases",
            ],
        )
        assert allowed is False
        assert msg is not None and len(msg) > 0

    def test_empty_criteria_is_blocked(self):
        allowed, msg = _simulate_planning_gate(
            name="Feature with no criteria",
            description="Does something important",
            criteria=[],
        )
        assert allowed is False

    def test_single_valid_ac_may_pass_or_be_low(self):
        """Even with one valid AC, the score may be too low due to AC coverage."""
        report = compute_score(
            name="Single AC feature",
            description="Expose compute_score.",
            acceptance_criteria=["pytest: tests/test_quality_score.py"],
        )
        # Just verify we get a meaningful score — not necessarily passing
        assert 0.0 <= report.score <= 1.0

    def test_blocked_message_is_structured_remediation_report(self):
        """The blocking message must be a structured report with score, threshold, hints."""
        allowed, msg = _simulate_planning_gate(
            name="Vague feature",
            description="Do everything",
            criteria=[
                "The code works",
                "It handles all cases",
            ],
        )
        assert allowed is False
        assert msg is not None
        # Must mention threshold and score for actionability
        assert "0.85" in msg or "85" in msg or "threshold" in msg.lower()

    def test_integration_criterion_that_is_reachable_passes(self):
        """A feature with a reachable integration target scores better."""
        report = compute_score(
            name="Integration feature",
            description="Wire quality scoring into bob.orchestrator.run_loop.",
            acceptance_criteria=[
                "integration: bob.orchestrator.run_loop",
                "Function defined: bob.spec_quality.quality_score.compute_score",
                "pytest: tests/test_quality_score.py",
            ],
        )
        # bob.orchestrator.run_loop should be reachable
        assert report.components.reachability_score > 0.0

    def test_gate_returns_two_tuple(self):
        """gate_for_ready must return exactly a 2-tuple (bool, str|None)."""
        from bob.spec_quality.quality_score import QualityReport, ScoreComponents
        report = QualityReport(
            score=0.5,
            components=ScoreComponents(
                ambiguity_score=0.5,
                reachability_score=0.5,
                ears_score=0.5,
                ac_coverage_score=0.5,
            ),
            remediation_hints=["Fix AC[0]"],
        )
        result = gate_for_ready(report)
        assert isinstance(result, tuple)
        assert len(result) == 2
        allowed, message = result
        assert isinstance(allowed, bool)
        assert message is None or isinstance(message, str)

    def test_score_is_persisted_on_feature_model(self):
        """Feature model must accept spec_quality_score field."""
        from bob.models import Feature
        from datetime import datetime

        f = Feature(
            id="test-id",
            project_id="proj-id",
            name="Test",
            spec_quality_score=0.92,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert f.spec_quality_score == 0.92

    def test_spec_quality_score_none_allowed(self):
        """spec_quality_score=None is valid (not yet computed)."""
        from bob.models import Feature
        from datetime import datetime

        f = Feature(
            id="test-id",
            project_id="proj-id",
            name="Test",
            spec_quality_score=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert f.spec_quality_score is None
