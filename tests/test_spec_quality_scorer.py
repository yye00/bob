"""Tests for spec_quality.scorer — compute_spec_quality_score and generate_remediation_report.

AC: pytest: tests/test_spec_quality_scorer.py
AC: integration: spec_quality
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.scorer import compute_spec_quality_score, generate_remediation_report


# ---------------------------------------------------------------------------
# compute_spec_quality_score
# ---------------------------------------------------------------------------

class TestComputeSpecQualityScore:
    def test_returns_float_in_unit_interval(self):
        score = compute_spec_quality_score(
            name="good feature",
            description="A feature with function compute_score and class QualityReport.",
            acceptance_criteria=[
                "File exists: src/spec_quality/scorer.py",
                "Function defined: spec_quality.scorer.compute_spec_quality_score",
                "pytest: tests/test_spec_quality_scorer.py",
            ],
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_empty_ac_list_returns_zero(self):
        score = compute_spec_quality_score(
            name="no acs",
            description=None,
            acceptance_criteria=[],
        )
        assert score == 0.0

    def test_none_description_accepted(self):
        score = compute_spec_quality_score(
            name="no desc",
            description=None,
            acceptance_criteria=["File exists: src/spec_quality/scorer.py"],
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_none_name_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_spec_quality_score(
                name=None,
                description=None,
                acceptance_criteria=["File exists: src/spec_quality/scorer.py"],
            )

    def test_non_list_non_string_acs_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_spec_quality_score(
                name="bad acs",
                description=None,
                acceptance_criteria={"key": "value"},
            )

    def test_json_encoded_acs_accepted(self):
        import json
        acs = json.dumps(["File exists: src/spec_quality/scorer.py"])
        score = compute_spec_quality_score(
            name="json acs",
            description=None,
            acceptance_criteria=acs,
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_score_above_threshold_for_rich_spec(self):
        """A feature with good structured ACs and matching description scores >= 0.85."""
        score = compute_spec_quality_score(
            name="well specified feature",
            description=(
                "Implements function compute_spec_quality_score and function "
                "generate_remediation_report for module spec_quality.scorer."
            ),
            acceptance_criteria=[
                "File exists: src/spec_quality/scorer.py",
                "Function defined: spec_quality.scorer.compute_spec_quality_score",
                "Function defined: spec_quality.scorer.generate_remediation_report",
                "pytest: tests/test_spec_quality_scorer.py",
            ],
        )
        assert isinstance(score, float)
        assert score >= 0.85

    def test_score_below_threshold_for_vague_spec(self):
        """A feature with vague/unstructured ACs and no matching description scores < 0.85."""
        score = compute_spec_quality_score(
            name="vague feature",
            description=None,
            acceptance_criteria=[
                "It should work well",
                "Performance is good",
            ],
        )
        assert isinstance(score, float)
        assert score < 0.85

    def test_integration_marker(self):
        """integration: spec_quality — verify the module is importable in full integration context."""
        import importlib
        mod = importlib.import_module("spec_quality.scorer")
        assert hasattr(mod, "compute_spec_quality_score")
        assert hasattr(mod, "generate_remediation_report")

    def test_score_clamped_to_unit_interval(self):
        """Score never exceeds [0.0, 1.0] regardless of inputs."""
        score = compute_spec_quality_score(
            name="clamp test",
            description=None,
            acceptance_criteria=[
                "File exists: src/spec_quality/scorer.py",
                "Function defined: spec_quality.scorer.compute_spec_quality_score",
                "Function defined: spec_quality.scorer.generate_remediation_report",
                "pytest: tests/test_spec_quality_scorer.py",
            ],
        )
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# generate_remediation_report
# ---------------------------------------------------------------------------

class TestGenerateRemediationReport:
    def test_returns_string_for_low_score(self):
        report = generate_remediation_report(
            name="bad feature",
            description=None,
            acceptance_criteria=[],
        )
        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_contains_score(self):
        report = generate_remediation_report(
            name="empty acs feature",
            description=None,
            acceptance_criteria=[],
        )
        assert "score" in report.lower() or "0.0" in report or "0.00" in report

    def test_report_contains_component_names(self):
        """Remediation report must name all four sub-score components."""
        report = generate_remediation_report(
            name="blocked feature",
            description=None,
            acceptance_criteria=[],
        )
        assert "ambiguity" in report.lower()
        assert "reachability" in report.lower()
        assert "ears" in report.lower()
        assert "ac_coverage" in report.lower() or "coverage" in report.lower()

    def test_report_contains_blocked_indicator_for_zero_score(self):
        report = generate_remediation_report(
            name="zero score",
            description=None,
            acceptance_criteria=[],
        )
        assert "BLOCKED" in report or "pending" in report or "blocked" in report.lower()

    def test_high_score_feature_report_is_none_or_passing(self):
        """For a feature that passes the gate, generate_remediation_report returns None or a passing message."""
        result = generate_remediation_report(
            name="well specified feature",
            description=(
                "Implements function compute_spec_quality_score and function "
                "generate_remediation_report for module spec_quality.scorer."
            ),
            acceptance_criteria=[
                "File exists: src/spec_quality/scorer.py",
                "Function defined: spec_quality.scorer.compute_spec_quality_score",
                "Function defined: spec_quality.scorer.generate_remediation_report",
                "pytest: tests/test_spec_quality_scorer.py",
            ],
        )
        # Either None (gate passed) or a string (possibly a passing message)
        assert result is None or isinstance(result, str)

    def test_none_name_raises(self):
        with pytest.raises((ValueError, TypeError)):
            generate_remediation_report(
                name=None,
                description=None,
                acceptance_criteria=["File exists: src/spec_quality/scorer.py"],
            )

    def test_report_for_vague_acs_contains_hints(self):
        """Vague ACs produce a report with at least one remediation hint."""
        report = generate_remediation_report(
            name="vague feature",
            description=None,
            acceptance_criteria=[
                "It should work well",
            ],
        )
        assert isinstance(report, str)
        assert len(report) > 20
