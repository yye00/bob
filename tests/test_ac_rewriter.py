"""Tests for bob.ac_rewriter — semantic-equivalence check and auto-repair."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.ac_rewriter import apply_semantic_equivalence_check, auto_repair_error_severity_ac


def _mock_llm_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


class TestApplySemanticEquivalenceCheck:
    """Tests for apply_semantic_equivalence_check."""

    def test_equivalent_rewrites_return_true(self):
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = apply_semantic_equivalence_check(
                "The system should process requests.",
                "The system shall process requests.",
            )
        assert is_equiv is True
        assert isinstance(rationale, str)

    def test_non_equivalent_rewrites_return_false(self):
        resp = _mock_llm_response("EQUIVALENT: false\nRATIONALE: Different constraint.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = apply_semantic_equivalence_check(
                "The system shall process requests within 200ms.",
                "The system shall process requests.",
            )
        assert is_equiv is False

    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError, match="original must be a string"):
            apply_semantic_equivalence_check(123, "rewrite")  # type: ignore[arg-type]

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError, match="rewrite must be a string"):
            apply_semantic_equivalence_check("original", None)  # type: ignore[arg-type]

    def test_llm_failure_returns_false_with_message(self):
        with patch("bob.auto_repair._call_llm_judge", side_effect=Exception("network error")):
            is_equiv, rationale = apply_semantic_equivalence_check("original", "rewrite")
        assert is_equiv is False
        assert "network error" in rationale or isinstance(rationale, str)

    def test_empty_string_inputs_return_false(self):
        with patch("bob.auto_repair._call_llm_judge", side_effect=Exception("empty")):
            is_equiv, rationale = apply_semantic_equivalence_check("", "")
        assert is_equiv is False

    def test_returns_tuple_of_bool_and_str(self):
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: OK.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            result = apply_semantic_equivalence_check("a", "a")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


class TestAutoRepairErrorSeverityAc:
    """Tests for auto_repair_error_severity_ac."""

    def _error_finding(self, text: str, rewrite: str) -> dict:
        return {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": text,
            "detail": "Uses 'should'.",
            "suggested_rewrite": rewrite,
        }

    def _warn_finding(self, text: str, rewrite: str) -> dict:
        return {
            "smell_id": "S02",
            "smell_name": "VagueQualifier",
            "severity": "W",
            "text": text,
            "detail": "Vague.",
            "suggested_rewrite": rewrite,
        }

    def test_error_severity_finding_is_applied_when_equivalent(self, tmp_path):
        original = "The system should process requests."
        rewrite = "The system shall process requests."
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            result = auto_repair_error_severity_ac(
                feature_id="feat-001",
                findings=[self._error_finding(original, rewrite)],
                original_acs=[original],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == [rewrite]
        assert len(result["repairs_applied"]) == 1
        assert result["repairs_applied"][0]["original"] == original
        assert result["repairs_applied"][0]["rewrite"] == rewrite

    def test_error_severity_finding_not_applied_when_not_equivalent(self, tmp_path):
        original = "The system shall process requests within 200ms."
        rewrite = "The system shall process requests."
        resp = _mock_llm_response("EQUIVALENT: false\nRATIONALE: Drops timing constraint.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            result = auto_repair_error_severity_ac(
                feature_id="feat-002",
                findings=[self._error_finding(original, rewrite)],
                original_acs=[original],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == [original]
        assert result["repairs_applied"] == []

    def test_warn_severity_finding_is_not_applied(self, tmp_path):
        original = "The system shall respond quickly."
        rewrite = "The system shall respond within 200ms."
        result = auto_repair_error_severity_ac(
            feature_id="feat-003",
            findings=[self._warn_finding(original, rewrite)],
            original_acs=[original],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == [original]
        assert result["repairs_applied"] == []

    def test_auto_repair_false_skips_all_repairs(self, tmp_path):
        original = "The system should process requests."
        rewrite = "The system shall process requests."
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: OK.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            result = auto_repair_error_severity_ac(
                feature_id="feat-004",
                findings=[self._error_finding(original, rewrite)],
                original_acs=[original],
                repairs_log=tmp_path / "repairs.log",
                auto_repair=False,
            )
        assert result["repaired_acs"] == [original]
        assert result["repairs_applied"] == []

    def test_empty_findings_returns_original_acs(self, tmp_path):
        result = auto_repair_error_severity_ac(
            feature_id="feat-005",
            findings=[],
            original_acs=["pytest: tests/test_foo.py"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py"]
        assert result["repairs_applied"] == []

    def test_non_string_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_error_severity_ac(
                feature_id=42,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_findings_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_error_severity_ac(
                feature_id="feat-006",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_original_acs_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            auto_repair_error_severity_ac(
                feature_id="feat-007",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_repair_log_is_written(self, tmp_path):
        original = "The system should respond."
        rewrite = "The system shall respond."
        log_path = tmp_path / "repairs.log"
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: OK.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            auto_repair_error_severity_ac(
                feature_id="feat-008",
                findings=[self._error_finding(original, rewrite)],
                original_acs=[original],
                repairs_log=log_path,
            )
        assert log_path.exists()
        assert log_path.stat().st_size > 0

    def test_multiple_error_findings_applied(self, tmp_path):
        ac1 = "The system should process requests."
        ac2 = "The module should validate inputs."
        rw1 = "The system shall process requests."
        rw2 = "The module shall validate inputs."
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            result = auto_repair_error_severity_ac(
                feature_id="feat-009",
                findings=[
                    self._error_finding(ac1, rw1),
                    self._error_finding(ac2, rw2),
                ],
                original_acs=[ac1, ac2],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == [rw1, rw2]
        assert len(result["repairs_applied"]) == 2


class TestLinterIntegration:
    """Verify ac_rewriter integrates with bob.linter."""

    def test_detects_smells_via_linter_and_repairs(self, tmp_path):
        from bob.linter import detect_smells

        ac = "The system should process requests."
        findings = detect_smells(ac)
        finding_dicts = [
            f._asdict() if hasattr(f, "_asdict") else vars(f) for f in findings
        ]
        resp = _mock_llm_response("EQUIVALENT: true\nRATIONALE: OK.")
        with patch("bob.auto_repair._call_llm_judge", return_value=resp):
            result = auto_repair_error_severity_ac(
                feature_id="feat-lint-001",
                findings=finding_dicts,
                original_acs=[ac],
                repairs_log=tmp_path / "repairs.log",
            )
        assert "repaired_acs" in result
        assert "repairs_applied" in result
        assert isinstance(result["repaired_acs"], list)
        assert len(result["repaired_acs"]) == 1
