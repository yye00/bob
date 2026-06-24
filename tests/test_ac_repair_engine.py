"""Tests for bob.ac_repair_engine — apply_semantic_equivalence_check and auto_repair_error_severity_rewrites."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.ac_repair_engine import (
    apply_semantic_equivalence_check,
    auto_repair_error_severity_rewrites,
)


# ---------------------------------------------------------------------------
# apply_semantic_equivalence_check
# ---------------------------------------------------------------------------

class TestApplySemanticEquivalenceCheck:
    def test_returns_true_when_judge_says_equivalent(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: Same constraint.")]
        with patch("bob.linter.auto_repair._call_llm_judge", return_value=mock_resp):
            result, rationale = apply_semantic_equivalence_check(
                "The system shall process requests.",
                "The system shall handle requests.",
            )
        assert result is True
        assert isinstance(rationale, str)

    def test_returns_false_when_judge_says_not_equivalent(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="EQUIVALENT: false\nRATIONALE: Different scope.")]
        with patch("bob.linter.auto_repair._call_llm_judge", return_value=mock_resp):
            result, rationale = apply_semantic_equivalence_check(
                "The system shall process requests.",
                "The system shall do nothing.",
            )
        assert result is False
        assert isinstance(rationale, str)

    def test_returns_false_on_llm_failure(self):
        with patch("bob.linter.auto_repair._call_llm_judge", side_effect=Exception("network error")):
            result, rationale = apply_semantic_equivalence_check("original", "rewrite")
        assert result is False
        assert "LLM judge call failed" in rationale

    def test_raises_value_error_for_non_string_original(self):
        with pytest.raises(ValueError):
            apply_semantic_equivalence_check(123, "rewrite")  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_rewrite(self):
        with pytest.raises(ValueError):
            apply_semantic_equivalence_check("original", None)  # type: ignore[arg-type]

    def test_empty_strings_do_not_raise(self):
        with patch("bob.linter.auto_repair._call_llm_judge", side_effect=Exception("empty")):
            result, rationale = apply_semantic_equivalence_check("", "")
        assert result is False
        assert isinstance(rationale, str)


# ---------------------------------------------------------------------------
# auto_repair_error_severity_rewrites
# ---------------------------------------------------------------------------

class TestAutoRepairErrorSeverityRewrites:
    def test_raises_value_error_for_non_string_feature_id(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_error_severity_rewrites(
                feature_id=42,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_non_list_findings(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_error_severity_rewrites(
                feature_id="feat-001",
                findings="bad",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_non_list_original_acs(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_error_severity_rewrites(
                feature_id="feat-001",
                findings=[],
                original_acs="bad",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_empty_inputs_return_empty_results(self, tmp_path):
        result = auto_repair_error_severity_rewrites(
            feature_id="feat-001",
            findings=[],
            original_acs=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == []
        assert result["repairs_applied"] == []

    def test_warn_severity_finding_not_applied(self, tmp_path):
        finding = {
            "smell_id": "S02",
            "smell_name": "VagueQualifier",
            "severity": "W",
            "text": "The system shall respond quickly.",
            "detail": "Vague qualifier.",
            "suggested_rewrite": "The system shall respond within 200ms.",
        }
        result = auto_repair_error_severity_rewrites(
            feature_id="feat-002",
            findings=[finding],
            original_acs=["The system shall respond quickly."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system shall respond quickly."]

    def test_error_severity_finding_applied_when_equivalent(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should' instead of 'shall'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: Same constraint.")]
        with patch("auto_repair._call_llm_judge", return_value=mock_resp):
            result = auto_repair_error_severity_rewrites(
                feature_id="feat-003",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert len(result["repairs_applied"]) == 1
        assert result["repaired_acs"] == ["The system shall process requests."]

    def test_error_severity_finding_not_applied_when_not_equivalent(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall do nothing.",
        }
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="EQUIVALENT: false\nRATIONALE: Different behavior.")]
        with patch("auto_repair._call_llm_judge", return_value=mock_resp):
            result = auto_repair_error_severity_rewrites(
                feature_id="feat-004",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should process requests."]

    def test_auto_repair_false_skips_all_rewrites(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        result = auto_repair_error_severity_rewrites(
            feature_id="feat-005",
            findings=[finding],
            original_acs=["The system should process requests."],
            auto_repair=False,
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should process requests."]

    def test_ac_without_smell_passes_through_unchanged(self, tmp_path):
        result = auto_repair_error_severity_rewrites(
            feature_id="feat-006",
            findings=[],
            original_acs=["pytest: tests/test_foo.py -v"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py -v"]
        assert result["repairs_applied"] == []

    def test_repair_log_written_when_repair_applied(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        log_file = tmp_path / "repairs.log"
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: OK.")]
        with patch("auto_repair._call_llm_judge", return_value=mock_resp):
            auto_repair_error_severity_rewrites(
                feature_id="feat-007",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=log_file,
            )
        assert log_file.exists()
        content = log_file.read_text()
        assert "feat-007" in content


# ---------------------------------------------------------------------------
# Integration: bob.linter → ac_repair_engine
# ---------------------------------------------------------------------------

class TestLinterIntegration:
    def test_importable_from_bob_linter(self):
        from bob.linter import detect_smells  # noqa: F401
        assert callable(detect_smells)

    def test_repair_engine_accepts_smell_finding_objects(self, tmp_path):
        """SmellFinding dataclass from bob.linter is accepted without conversion."""
        from bob.spec_quality.smell_detectors import SmellFinding

        finding = SmellFinding(
            smell_id="S09",
            smell_name="Shall-vs-Should",
            severity="E",
            text="The system should process requests.",
            detail="Uses 'should'.",
            suggested_rewrite="The system shall process requests.",
        )
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: OK.")]
        with patch("auto_repair._call_llm_judge", return_value=mock_resp):
            result = auto_repair_error_severity_rewrites(
                feature_id="feat-int-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert len(result["repairs_applied"]) == 1
        assert result["repaired_acs"] == ["The system shall process requests."]
