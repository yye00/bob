"""Tests for bob3.semantic_repair — verify_semantic_equivalence and apply_auto_repair."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.semantic_repair import verify_semantic_equivalence, apply_auto_repair
from bob3.linter import SmellFinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def _equiv_true() -> MagicMock:
    return _llm_response("EQUIVALENT: true\nRATIONALE: Same observable constraint.")


def _equiv_false() -> MagicMock:
    return _llm_response("EQUIVALENT: false\nRATIONALE: Different constraint.")


def _make_error_finding(text: str = "The system should process requests.") -> SmellFinding:
    return SmellFinding(
        smell_id="S09",
        smell_name="Shall-vs-Should",
        severity="E",
        text=text,
        detail="Uses 'should' where 'shall' is required.",
        suggested_rewrite="The system shall process requests.",
    )


def _make_warn_finding(text: str = "The system shall respond quickly.") -> SmellFinding:
    return SmellFinding(
        smell_id="S02",
        smell_name="VagueQualifier",
        severity="W",
        text=text,
        detail="Vague performance qualifier.",
        suggested_rewrite="The system shall respond within 200ms.",
    )


# ---------------------------------------------------------------------------
# verify_semantic_equivalence
# ---------------------------------------------------------------------------

class TestVerifySemanticEquivalence:
    def test_returns_true_when_llm_says_equivalent(self):
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_true()):
            result, rationale = verify_semantic_equivalence("original text", "rewrite text")
        assert result is True
        assert "Same observable" in rationale

    def test_returns_false_when_llm_says_not_equivalent(self):
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_false()):
            result, rationale = verify_semantic_equivalence("original text", "different rewrite")
        assert result is False
        assert isinstance(rationale, str)

    def test_returns_false_on_llm_exception(self):
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", side_effect=Exception("network error")):
            result, rationale = verify_semantic_equivalence("original", "rewrite")
        assert result is False
        assert "LLM judge call failed" in rationale

    def test_raises_value_error_for_non_string_original(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence(123, "rewrite")  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_rewrite(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence("original", None)  # type: ignore[arg-type]

    def test_raises_value_error_for_both_none(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence(None, None)  # type: ignore[arg-type]

    def test_identical_strings_passes(self):
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_true()):
            result, rationale = verify_semantic_equivalence("same text", "same text")
        assert isinstance(result, bool)
        assert isinstance(rationale, str)

    def test_empty_strings_on_llm_error_returns_false(self):
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", side_effect=Exception("empty")):
            result, rationale = verify_semantic_equivalence("", "")
        assert result is False


# ---------------------------------------------------------------------------
# apply_auto_repair
# ---------------------------------------------------------------------------

class TestApplyAutoRepair:
    def test_empty_findings_returns_original_acs(self, tmp_path: Path):
        result = apply_auto_repair(
            feature_id="feat-001",
            findings=[],
            original_acs=["pytest: tests/test_foo.py -v"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py -v"]
        assert result["repairs_applied"] == []

    def test_error_finding_repaired_when_equivalent(self, tmp_path: Path):
        finding = _make_error_finding()
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_true()):
            result = apply_auto_repair(
                feature_id="feat-002",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1
        assert result["repairs_applied"][0]["smell_id"] == "S09"

    def test_warn_finding_not_auto_applied(self, tmp_path: Path):
        finding = _make_warn_finding()
        result = apply_auto_repair(
            feature_id="feat-003",
            findings=[finding],
            original_acs=["The system shall respond quickly."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system shall respond quickly."]
        assert result["repairs_applied"] == []

    def test_error_finding_not_applied_when_not_equivalent(self, tmp_path: Path):
        finding = _make_error_finding()
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_false()):
            result = apply_auto_repair(
                feature_id="feat-004",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_auto_repair_false_skips_all_repairs(self, tmp_path: Path):
        finding = _make_error_finding()
        result = apply_auto_repair(
            feature_id="feat-005",
            findings=[finding],
            original_acs=["The system should process requests."],
            auto_repair=False,
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_repair_log_written(self, tmp_path: Path):
        finding = _make_error_finding()
        log_path = tmp_path / "repairs.log"
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_true()):
            apply_auto_repair(
                feature_id="feat-006",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=log_path,
            )
        assert log_path.exists()
        content = log_path.read_text()
        assert "feat-006" in content

    def test_dict_finding_accepted(self, tmp_path: Path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_true()):
            result = apply_auto_repair(
                feature_id="feat-007",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1

    def test_raises_value_error_for_non_string_feature_id(self, tmp_path: Path):
        with pytest.raises(ValueError):
            apply_auto_repair(
                feature_id=123,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_non_list_findings(self, tmp_path: Path):
        with pytest.raises(ValueError):
            apply_auto_repair(
                feature_id="feat-err-001",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_non_list_acs(self, tmp_path: Path):
        with pytest.raises(ValueError):
            apply_auto_repair(
                feature_id="feat-err-002",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_none_feature_id_raises_value_error(self, tmp_path: Path):
        with pytest.raises(ValueError):
            apply_auto_repair(
                feature_id=None,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_finding_without_suggested_rewrite_skipped(self, tmp_path: Path):
        finding = SmellFinding(
            smell_id="S09",
            smell_name="Shall-vs-Should",
            severity="E",
            text="The system should process requests.",
            detail="Uses 'should'.",
            suggested_rewrite=None,
        )
        result = apply_auto_repair(
            feature_id="feat-008",
            findings=[finding],
            original_acs=["The system should process requests."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []


# ---------------------------------------------------------------------------
# Integration with bob3.linter
# ---------------------------------------------------------------------------

class TestLinterIntegration:
    def test_detect_smells_returns_smell_findings_compatible_with_apply_auto_repair(self, tmp_path: Path):
        from bob3.linter import detect_smells

        text = "The system should process requests."
        findings = detect_smells(text)
        # findings from the linter should be accepted by apply_auto_repair
        result = apply_auto_repair(
            feature_id="feat-linter-001",
            findings=findings,
            original_acs=[text],
            auto_repair=False,
            repairs_log=tmp_path / "repairs.log",
        )
        assert isinstance(result["repaired_acs"], list)
        assert result["repaired_acs"] == [text]

    def test_linter_findings_with_error_severity_can_be_repaired(self, tmp_path: Path):
        from bob3.linter import detect_smells, filter_by_severity

        text = "The system should process requests."
        all_findings = detect_smells(text)
        error_findings = filter_by_severity(all_findings, "E")

        if not error_findings:
            pytest.skip("No ERROR-severity findings detected for this AC text")

        for f in error_findings:
            f.suggested_rewrite = f"The system shall process requests."

        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_equiv_true()):
            result = apply_auto_repair(
                feature_id="feat-linter-002",
                findings=error_findings,
                original_acs=[text],
                repairs_log=tmp_path / "repairs.log",
            )
        assert isinstance(result["repaired_acs"], list)
        assert isinstance(result["repairs_applied"], list)
