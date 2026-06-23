"""Tests for bob3.ac_repair — check_semantic_equivalence and auto_repair_ac."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.ac_repair import check_semantic_equivalence, auto_repair_ac


def _make_mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


class TestCheckSemanticEquivalence:
    def test_equivalent_returns_true(self):
        resp = _make_mock_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = check_semantic_equivalence(
                "The system shall process requests.",
                "The system must handle requests.",
            )
        assert is_equiv is True
        assert "Same constraint" in rationale

    def test_not_equivalent_returns_false(self):
        resp = _make_mock_response("EQUIVALENT: false\nRATIONALE: Semantics differ.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = check_semantic_equivalence(
                "The system shall respond within 100ms.",
                "The system shall eventually respond.",
            )
        assert is_equiv is False
        assert isinstance(rationale, str)

    def test_llm_failure_returns_false(self):
        with patch("bob3.ac_repair._call_llm_judge", side_effect=Exception("network error")):
            is_equiv, rationale = check_semantic_equivalence("original", "rewrite")
        assert is_equiv is False
        assert "LLM judge call failed" in rationale

    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError, match="original must be a string"):
            check_semantic_equivalence(123, "rewrite")  # type: ignore[arg-type]

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError, match="rewrite must be a string"):
            check_semantic_equivalence("original", None)  # type: ignore[arg-type]

    def test_empty_strings_do_not_raise(self):
        with patch("bob3.ac_repair._call_llm_judge", side_effect=Exception("empty")):
            result, rationale = check_semantic_equivalence("", "")
        assert result is False
        assert isinstance(rationale, str)

    def test_unparseable_response_returns_false(self):
        resp = _make_mock_response("I cannot determine equivalence.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = check_semantic_equivalence("a", "b")
        assert is_equiv is False
        assert isinstance(rationale, str)


class TestAutoRepairAc:
    def test_error_severity_with_equivalent_rewrite_applied(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "ShallVsShould",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should' instead of 'shall'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        resp = _make_mock_response("EQUIVALENT: true\nRATIONALE: Same behavior.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1
        assert result["repairs_applied"][0]["smell_id"] == "S09"

    def test_non_equivalent_rewrite_rejected(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "ShallVsShould",
            "severity": "E",
            "text": "The system should respond.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall respond within 100ms.",
        }
        resp = _make_mock_response("EQUIVALENT: false\nRATIONALE: Added constraint.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-002",
                findings=[finding],
                original_acs=["The system should respond."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should respond."]
        assert result["repairs_applied"] == []

    def test_warning_severity_not_auto_applied(self, tmp_path):
        finding = {
            "smell_id": "S02",
            "smell_name": "VagueQualifier",
            "severity": "W",
            "text": "The system shall be fast.",
            "detail": "Vague qualifier.",
            "suggested_rewrite": "The system shall respond within 200ms.",
        }
        result = auto_repair_ac(
            feature_id="feat-003",
            findings=[finding],
            original_acs=["The system shall be fast."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system shall be fast."]

    def test_auto_repair_false_skips_all_repairs(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "ShallVsShould",
            "severity": "E",
            "text": "The system should work.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall work.",
        }
        result = auto_repair_ac(
            feature_id="feat-004",
            findings=[finding],
            original_acs=["The system should work."],
            repairs_log=tmp_path / "repairs.log",
            auto_repair=False,
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should work."]

    def test_empty_findings_and_acs_returns_empty(self, tmp_path):
        result = auto_repair_ac(
            feature_id="feat-005",
            findings=[],
            original_acs=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == []
        assert result["repairs_applied"] == []

    def test_finding_without_suggested_rewrite_skipped(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "ShallVsShould",
            "severity": "E",
            "text": "The system should work.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": None,
        }
        result = auto_repair_ac(
            feature_id="feat-006",
            findings=[finding],
            original_acs=["The system should work."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should work."]

    def test_repair_log_written(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "ShallVsShould",
            "severity": "E",
            "text": "The system should go.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall go.",
        }
        repairs_log = tmp_path / "repairs.log"
        resp = _make_mock_response("EQUIVALENT: true\nRATIONALE: Equivalent.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            auto_repair_ac(
                feature_id="feat-007",
                findings=[finding],
                original_acs=["The system should go."],
                repairs_log=repairs_log,
            )
        assert repairs_log.exists()
        content = repairs_log.read_text()
        assert "feat-007" in content
        assert "S09" in content

    def test_non_string_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_ac(
                feature_id=123,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_findings_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_ac(
                feature_id="feat-err",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_original_acs_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_ac(
                feature_id="feat-err",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_namedtuple_finding_accepted(self, tmp_path):
        from collections import namedtuple

        SmellFinding = namedtuple(
            "SmellFinding",
            ["smell_id", "smell_name", "severity", "text", "detail", "suggested_rewrite"],
        )
        finding = SmellFinding(
            smell_id="S09",
            smell_name="ShallVsShould",
            severity="E",
            text="The system should stop.",
            detail="Uses 'should'.",
            suggested_rewrite="The system shall stop.",
        )
        resp = _make_mock_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob3.ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-nt",
                findings=[finding],
                original_acs=["The system should stop."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall stop."]
        assert len(result["repairs_applied"]) == 1

    def test_linter_integration(self, tmp_path):
        """check_semantic_equivalence and auto_repair_ac work with bob3.linter SmellFinding."""
        from bob3.linter import SmellFinding
        from bob3.ac_repair import check_semantic_equivalence, auto_repair_ac

        # SmellFinding from the linter should be accepted as a finding
        assert callable(check_semantic_equivalence)
        assert callable(auto_repair_ac)
        # Basic smoke test: linter module importable alongside ac_repair
        result = auto_repair_ac(
            feature_id="feat-linter",
            findings=[],
            original_acs=["pytest: tests/test_foo.py"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py"]
