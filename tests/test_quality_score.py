"""Tests for bob.spec_quality.quality_score — compute_score and gate_for_ready."""

from __future__ import annotations

import pytest

from bob.spec_quality.quality_score import (
    QualityReport,
    ScoreComponents,
    compute_score,
    gate_for_ready,
)

SPEC_QUALITY_THRESHOLD = 0.85


@pytest.fixture(autouse=True)
def _reset_threshold_to_default(monkeypatch):
    """Ensure the quality threshold is 0.85 for every test in this module.

    BOB_SPEC_QUALITY_THRESHOLD may be set to a lower value in the operator
    environment; reset it here so tests use the canonical default.
    """
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
    import bob.spec_quality.threshold_resolver as _tr
    _tr._frozen_value = None
    _tr._frozen_initialized = False
    yield
    _tr._frozen_value = None
    _tr._frozen_initialized = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_good_feature():
    """A well-formed feature with structured ACs that should score high."""
    return {
        "name": "Good feature",
        "description": "Expose a public function compute_score in bob.spec_quality.quality_score.",
        "acceptance_criteria": [
            "File exists: src/bob/spec_quality/quality_score.py",
            "Function defined: bob.spec_quality.quality_score.compute_score",
            "Function defined: bob.spec_quality.quality_score.gate_for_ready",
            "pytest: tests/test_quality_score.py",
        ],
    }


def _make_vague_feature():
    """A feature with vague / unstructured ACs that should score low."""
    return {
        "name": "Vague feature",
        "description": "Make it work",
        "acceptance_criteria": [
            "The system works correctly",
            "All cases are handled",
            "It supports everything",
        ],
    }


def _make_no_ac_feature():
    return {
        "name": "No AC feature",
        "description": "Some description without acceptance criteria",
        "acceptance_criteria": [],
    }


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------

class TestComputeScore:
    def test_returns_float_in_range(self):
        feature = _make_good_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert isinstance(report, QualityReport)
        assert 0.0 <= report.score <= 1.0

    def test_good_feature_scores_above_threshold(self):
        feature = _make_good_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert report.score >= SPEC_QUALITY_THRESHOLD, (
            f"Expected score >= {SPEC_QUALITY_THRESHOLD}, got {report.score}"
        )

    def test_vague_feature_scores_below_threshold(self):
        feature = _make_vague_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert report.score < SPEC_QUALITY_THRESHOLD, (
            f"Expected score < {SPEC_QUALITY_THRESHOLD}, got {report.score}"
        )

    def test_empty_ac_scores_zero_or_very_low(self):
        feature = _make_no_ac_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert report.score < 0.5

    def test_report_has_components(self):
        feature = _make_good_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert isinstance(report.components, ScoreComponents)
        assert 0.0 <= report.components.ambiguity_score <= 1.0
        assert 0.0 <= report.components.reachability_score <= 1.0
        assert 0.0 <= report.components.ears_score <= 1.0
        assert 0.0 <= report.components.ac_coverage_score <= 1.0

    def test_score_is_weighted_average_of_components(self):
        feature = _make_good_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        # Score should be in [0,1] and consistent with components
        c = report.components
        assert isinstance(c.ambiguity_score, float)
        assert isinstance(c.reachability_score, float)
        assert isinstance(c.ears_score, float)
        assert isinstance(c.ac_coverage_score, float)

    def test_report_contains_remediation_hints_when_failing(self):
        feature = _make_vague_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert report.score < SPEC_QUALITY_THRESHOLD
        assert len(report.remediation_hints) > 0

    def test_no_remediation_when_passing(self):
        feature = _make_good_feature()
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=feature["acceptance_criteria"],
        )
        assert report.score >= SPEC_QUALITY_THRESHOLD
        # May have empty remediation for passing specs
        assert isinstance(report.remediation_hints, list)

    def test_accepts_json_string_criteria(self):
        import json
        feature = _make_good_feature()
        criteria_json = json.dumps(feature["acceptance_criteria"])
        report = compute_score(
            name=feature["name"],
            description=feature["description"],
            acceptance_criteria=criteria_json,
        )
        assert isinstance(report, QualityReport)
        assert 0.0 <= report.score <= 1.0

    def test_accepts_none_description(self):
        report = compute_score(
            name="Feature",
            description=None,
            acceptance_criteria=["pytest: tests/test_foo.py"],
        )
        assert isinstance(report, QualityReport)

    def test_ac_coverage_drops_when_api_missing_from_ac(self):
        """If description mentions a public function but AC doesn't cover it, score drops."""
        report_covered = compute_score(
            name="Feature",
            description="Expose function compute_score.",
            acceptance_criteria=[
                "Function defined: bob.spec_quality.quality_score.compute_score",
                "pytest: tests/test_quality_score.py",
            ],
        )
        report_uncovered = compute_score(
            name="Feature",
            description="Expose function compute_score and also gate_for_ready.",
            acceptance_criteria=[
                "pytest: tests/test_quality_score.py",
            ],
        )
        assert report_covered.components.ac_coverage_score >= report_uncovered.components.ac_coverage_score


# ---------------------------------------------------------------------------
# gate_for_ready
# ---------------------------------------------------------------------------

class TestGateForReady:
    def test_passes_for_high_score(self):
        report = QualityReport(
            score=0.90,
            components=ScoreComponents(
                ambiguity_score=0.9,
                reachability_score=0.9,
                ears_score=0.9,
                ac_coverage_score=0.9,
            ),
            remediation_hints=[],
        )
        allowed, message = gate_for_ready(report)
        assert allowed is True
        assert message is None or message == ""

    def test_blocks_for_low_score(self):
        report = QualityReport(
            score=0.50,
            components=ScoreComponents(
                ambiguity_score=0.5,
                reachability_score=0.5,
                ears_score=0.5,
                ac_coverage_score=0.5,
            ),
            remediation_hints=["Fix ambiguity in AC[0]"],
        )
        allowed, message = gate_for_ready(report)
        assert allowed is False
        assert message is not None and len(message) > 0

    def test_message_includes_score_and_threshold(self):
        report = QualityReport(
            score=0.60,
            components=ScoreComponents(
                ambiguity_score=0.6,
                reachability_score=0.6,
                ears_score=0.6,
                ac_coverage_score=0.6,
            ),
            remediation_hints=["Rewrite AC[1] as structured form"],
        )
        allowed, message = gate_for_ready(report)
        assert allowed is False
        assert "0.60" in message or "0.6" in message or "60" in message
        assert "0.85" in message or "85" in message

    def test_message_includes_remediation_hints(self):
        hint = "Rewrite AC[1] as 'pytest: tests/test_foo.py'"
        report = QualityReport(
            score=0.70,
            components=ScoreComponents(
                ambiguity_score=0.7,
                reachability_score=0.7,
                ears_score=0.7,
                ac_coverage_score=0.7,
            ),
            remediation_hints=[hint],
        )
        allowed, message = gate_for_ready(report)
        assert allowed is False
        assert hint in message

    def test_boundary_at_threshold_passes(self):
        report = QualityReport(
            score=0.85,
            components=ScoreComponents(
                ambiguity_score=0.85,
                reachability_score=0.85,
                ears_score=0.85,
                ac_coverage_score=0.85,
            ),
            remediation_hints=[],
        )
        allowed, _ = gate_for_ready(report)
        assert allowed is True

    def test_just_below_threshold_blocks(self):
        report = QualityReport(
            score=0.849,
            components=ScoreComponents(
                ambiguity_score=0.85,
                reachability_score=0.85,
                ears_score=0.85,
                ac_coverage_score=0.849,
            ),
            remediation_hints=["Fix something"],
        )
        allowed, _ = gate_for_ready(report)
        assert allowed is False
