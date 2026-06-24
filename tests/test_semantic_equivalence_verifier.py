"""Tests for bob.semantic_equivalence_verifier."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.semantic_equivalence_verifier import auto_repair_ac, verify_semantic_equivalence


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


class TestVerifySemanticEquivalence:
    def test_equivalent_returns_true(self):
        resp = _mock_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = verify_semantic_equivalence(
                "The system shall process requests.",
                "The system must process requests.",
            )
        assert is_equiv is True
        assert "Same constraint" in rationale

    def test_not_equivalent_returns_false(self):
        resp = _mock_response("EQUIVALENT: false\nRATIONALE: Different meaning.")
        with patch("bob.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = verify_semantic_equivalence(
                "The system shall process requests.",
                "The system shall reject all requests.",
            )
        assert is_equiv is False
        assert isinstance(rationale, str)

    def test_llm_failure_returns_false(self):
        with patch(
            "bob.linter_ac_repair._call_llm_judge", side_effect=Exception("LLM down")
        ):
            is_equiv, rationale = verify_semantic_equivalence("original", "rewrite")
        assert is_equiv is False
        assert "LLM" in rationale or "failed" in rationale.lower()

    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence(123, "rewrite")  # type: ignore[arg-type]

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence("original", None)  # type: ignore[arg-type]

    def test_empty_strings_return_false_on_llm_error(self):
        with patch(
            "bob.linter_ac_repair._call_llm_judge", side_effect=Exception("empty")
        ):
            result, rationale = verify_semantic_equivalence("", "")
        assert result is False
        assert isinstance(rationale, str)

    def test_identical_strings_do_not_raise(self):
        resp = _mock_response("EQUIVALENT: true\nRATIONALE: Identical.")
        with patch("bob.linter_ac_repair._call_llm_judge", return_value=resp):
            result, rationale = verify_semantic_equivalence("same text", "same text")
        assert isinstance(result, bool)
        assert isinstance(rationale, str)


class TestAutoRepairAc:
    def test_error_severity_with_equivalent_rewrite_applies(self, tmp_path: Path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        resp = _mock_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1
        assert result["repairs_applied"][0]["smell_id"] == "S09"

    def test_error_severity_non_equivalent_rewrite_skipped(self, tmp_path: Path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall reject requests.",
        }
        resp = _mock_response("EQUIVALENT: false\nRATIONALE: Different meaning.")
        with patch("bob.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-002",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_warn_severity_finding_not_auto_applied(self, tmp_path: Path):
        finding = {
            "smell_id": "S02",
            "smell_name": "VagueQualifier",
            "severity": "W",
            "text": "The system shall respond quickly.",
            "detail": "Vague qualifier.",
            "suggested_rewrite": "The system shall respond within 200ms.",
        }
        result = auto_repair_ac(
            feature_id="feat-003",
            findings=[finding],
            original_acs=["The system shall respond quickly."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system shall respond quickly."]

    def test_opt_out_skips_all_repairs(self, tmp_path: Path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        result = auto_repair_ac(
            feature_id="feat-004",
            findings=[finding],
            original_acs=["The system should process requests."],
            repairs_log=tmp_path / "repairs.log",
            auto_repair=False,
        )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_empty_findings_returns_original_acs(self, tmp_path: Path):
        result = auto_repair_ac(
            feature_id="feat-005",
            findings=[],
            original_acs=["pytest: tests/test_foo.py"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py"]
        assert result["repairs_applied"] == []

    def test_invalid_feature_id_raises_value_error(self, tmp_path: Path):
        with pytest.raises(ValueError):
            auto_repair_ac(
                feature_id=None,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_invalid_findings_type_raises_value_error(self, tmp_path: Path):
        with pytest.raises(ValueError):
            auto_repair_ac(
                feature_id="feat-006",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_invalid_original_acs_type_raises_value_error(self, tmp_path: Path):
        with pytest.raises(ValueError):
            auto_repair_ac(
                feature_id="feat-007",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_repair_logged_to_file(self, tmp_path: Path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        log_path = tmp_path / "repairs.log"
        resp = _mock_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob.linter_ac_repair._call_llm_judge", return_value=resp):
            auto_repair_ac(
                feature_id="feat-008",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=log_path,
            )
        assert log_path.exists()
        content = log_path.read_text()
        assert "feat-008" in content
        assert "S09" in content
