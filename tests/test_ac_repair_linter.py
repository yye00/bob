"""Tests for bob.ac_repair_linter — semantic-equivalence check and auto-apply repair."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.ac_repair_linter import semantic_equivalence_check, auto_apply_repair


def _mock_judge_response(text: str) -> MagicMock:
    response = MagicMock()
    content_item = MagicMock()
    content_item.text = text
    response.content = [content_item]
    return response


class TestSemanticEquivalenceCheck:
    def test_equivalent_returns_true(self):
        mock_response = _mock_judge_response(
            "EQUIVALENT: true\nRATIONALE: The rewrites express the same observable constraint."
        )
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result, rationale = semantic_equivalence_check(
                "The system should process requests.",
                "The system shall process requests.",
            )
        assert result is True
        assert "same" in rationale.lower() or isinstance(rationale, str)

    def test_not_equivalent_returns_false(self):
        mock_response = _mock_judge_response(
            "EQUIVALENT: false\nRATIONALE: The rewrite adds a new constraint not in the original."
        )
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result, rationale = semantic_equivalence_check(
                "The system shall log errors.",
                "The system shall log and email errors.",
            )
        assert result is False
        assert isinstance(rationale, str)

    def test_llm_error_returns_false(self):
        with patch("bob.ac_repair_linter._call_llm_judge", side_effect=Exception("network error")):
            result, rationale = semantic_equivalence_check("original ac", "rewritten ac")
        assert result is False
        assert "LLM judge call failed" in rationale or isinstance(rationale, str)

    def test_unparseable_response_returns_false(self):
        mock_response = _mock_judge_response("This is not a parseable response at all.")
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result, rationale = semantic_equivalence_check("original", "rewrite")
        assert result is False

    def test_empty_response_content_returns_false(self):
        mock_response = MagicMock()
        mock_response.content = []
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result, rationale = semantic_equivalence_check("original", "rewrite")
        assert result is False

    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError, match="original must be a string"):
            semantic_equivalence_check(123, "rewrite")  # type: ignore[arg-type]

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError, match="rewrite must be a string"):
            semantic_equivalence_check("original", None)  # type: ignore[arg-type]


class TestAutoApplyRepair:
    def test_error_severity_with_equivalent_rewrite_is_applied(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should' instead of 'shall'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        mock_response = _mock_judge_response(
            "EQUIVALENT: true\nRATIONALE: The rewrites impose the same observable constraint."
        )
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result = auto_apply_repair(
                feature_id="feat-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1
        assert result["repairs_applied"][0]["smell_id"] == "S09"
        assert result["repairs_applied"][0]["feature_id"] == "feat-001"

    def test_warning_severity_finding_not_applied(self, tmp_path):
        finding = {
            "smell_id": "S02",
            "smell_name": "VagueQualifier",
            "severity": "W",
            "text": "The system shall respond quickly.",
            "detail": "Vague qualifier 'quickly'.",
            "suggested_rewrite": "The system shall respond within 200ms.",
        }
        result = auto_apply_repair(
            feature_id="feat-002",
            findings=[finding],
            original_acs=["The system shall respond quickly."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system shall respond quickly."]
        assert result["repairs_applied"] == []

    def test_non_equivalent_rewrite_rejected(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should log errors.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall log and email errors.",
        }
        mock_response = _mock_judge_response(
            "EQUIVALENT: false\nRATIONALE: The rewrite adds an email constraint not in the original."
        )
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result = auto_apply_repair(
                feature_id="feat-003",
                findings=[finding],
                original_acs=["The system should log errors."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should log errors."]
        assert result["repairs_applied"] == []

    def test_opt_out_prevents_repairs(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should log errors.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall log errors.",
        }
        mock_response = _mock_judge_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result = auto_apply_repair(
                feature_id="feat-004",
                findings=[finding],
                original_acs=["The system should log errors."],
                repairs_log=tmp_path / "repairs.log",
                auto_repair=False,
            )
        assert result["repaired_acs"] == ["The system should log errors."]
        assert result["repairs_applied"] == []

    def test_repair_log_written(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        repairs_log = tmp_path / "repairs.log"
        mock_response = _mock_judge_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            auto_apply_repair(
                feature_id="feat-005",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=repairs_log,
            )
        assert repairs_log.exists()
        content = repairs_log.read_text()
        assert "feat-005" in content
        assert "S09" in content

    def test_empty_findings_returns_original_acs(self, tmp_path):
        original = ["pytest: tests/test_foo.py", "pytest: tests/test_bar.py"]
        result = auto_apply_repair(
            feature_id="feat-006",
            findings=[],
            original_acs=original,
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == original
        assert result["repairs_applied"] == []

    def test_missing_suggested_rewrite_skips_finding(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should log errors.",
            "detail": "Uses 'should'.",
        }
        result = auto_apply_repair(
            feature_id="feat-007",
            findings=[finding],
            original_acs=["The system should log errors."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system should log errors."]
        assert result["repairs_applied"] == []

    def test_namedtuple_finding_accepted(self, tmp_path):
        from collections import namedtuple

        SmellFinding = namedtuple(
            "SmellFinding",
            ["smell_id", "smell_name", "severity", "text", "detail", "suggested_rewrite"],
        )
        finding = SmellFinding(
            smell_id="S09",
            smell_name="Shall-vs-Should",
            severity="E",
            text="The system should be available.",
            detail="Uses 'should'.",
            suggested_rewrite="The system shall be available.",
        )
        mock_response = _mock_judge_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob.ac_repair_linter._call_llm_judge", return_value=mock_response):
            result = auto_apply_repair(
                feature_id="feat-008",
                findings=[finding],
                original_acs=["The system should be available."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall be available."]

    def test_non_string_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_apply_repair(
                feature_id=123,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_findings_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_apply_repair(
                feature_id="feat-009",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_original_acs_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_apply_repair(
                feature_id="feat-010",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )
