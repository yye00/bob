"""Tests boundary case: suggest_rewrite([]) returns empty list when no smells detected."""

from __future__ import annotations

from unittest.mock import patch

from bob.spec_quality.ac_auto_repair import (
    apply_repairs,
    repair_feature_acs,
    suggest_rewrite,
)
from bob.spec_quality.smell_detectors import SmellFinding


class TestBoundaryEmptySmellList:
    """Boundary: suggest_rewrite / repair functions with empty smell list."""

    def test_apply_repairs_empty_findings_returns_empty(self, tmp_path):
        repairs = apply_repairs(
            findings=[],
            feature_id="feat-empty",
            repairs_log=tmp_path / "repairs.log",
        )
        assert repairs == []

    def test_repair_feature_acs_empty_criteria_returns_empty(self, tmp_path):
        result = repair_feature_acs(
            feature_id="feat-empty",
            acceptance_criteria=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == []
        assert result["repairs_applied"] == []
        assert result["smell_findings"] == []

    def test_suggest_rewrite_info_severity_returns_none_for_info_finding(self):
        finding = SmellFinding(
            smell_id="S01",
            smell_name="informational",
            severity="I",
            text="The system shall handle edge cases.",
            detail="Info only.",
        )
        # Info-severity findings always return None
        result = suggest_rewrite(finding)
        assert result is None

    def test_apply_repairs_no_error_findings_returns_empty(self, tmp_path):
        warn_finding = SmellFinding(
            smell_id="S02",
            smell_name="vague-term",
            severity="W",
            text="The system shall respond quickly.",
            detail="Vague term.",
        )
        repairs = apply_repairs(
            findings=[warn_finding],
            feature_id="feat-warn-only",
            repairs_log=tmp_path / "repairs.log",
        )
        assert repairs == []

    def test_repair_feature_acs_all_clean_acs_no_repairs(self, tmp_path):
        with patch(
            "bob.spec_quality.ac_auto_repair.detect_all",
            return_value=[],
        ):
            result = repair_feature_acs(
                feature_id="feat-clean",
                acceptance_criteria=["The system shall log all events."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repairs_applied"] == []
        assert result["smell_findings"] == []
        assert result["repaired_acs"] == ["The system shall log all events."]

    def test_suggest_rewrite_empty_list_returns_empty_list(self):
        result = suggest_rewrite([])
        assert result == []
