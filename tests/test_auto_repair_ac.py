"""Tests for src/auto_repair_ac.py — semantic_equivalence_check and apply_error_severity_rewrites."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import auto_repair_ac
from auto_repair_ac import semantic_equivalence_check, apply_error_severity_rewrites


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(severity: str = "E", text: str = "The system should process requests.") -> dict:
    return {
        "smell_id": "S09",
        "smell_name": "Shall-vs-Should",
        "severity": severity,
        "text": text,
        "detail": "Uses 'should' where 'shall' is required.",
        "suggested_rewrite": "The system shall process requests.",
    }


def _mock_llm_equiv(is_equiv: bool) -> MagicMock:
    resp = MagicMock()
    flag = "true" if is_equiv else "false"
    resp.content = [MagicMock(text=f"EQUIVALENT: {flag}\nRATIONALE: Test rationale.")]
    return resp


# ---------------------------------------------------------------------------
# semantic_equivalence_check tests
# ---------------------------------------------------------------------------


class TestSemanticEquivalenceCheck:
    def test_returns_true_when_equivalent(self):
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result, rationale = semantic_equivalence_check(
                "The system should process requests.",
                "The system shall process requests.",
            )
        assert result is True
        assert isinstance(rationale, str)
        assert len(rationale) > 0

    def test_returns_false_when_not_equivalent(self):
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(False)):
            result, rationale = semantic_equivalence_check(
                "The system should process requests.",
                "The system shall never process requests.",
            )
        assert result is False
        assert isinstance(rationale, str)

    def test_llm_failure_returns_false(self):
        with patch("auto_repair._call_llm_judge", side_effect=Exception("network error")):
            result, rationale = semantic_equivalence_check(
                "The system shall store data.",
                "The system shall persist data.",
            )
        assert result is False
        assert "LLM judge call failed" in rationale

    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError):
            semantic_equivalence_check(42, "rewrite")  # type: ignore[arg-type]

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError):
            semantic_equivalence_check("original", None)  # type: ignore[arg-type]

    def test_returns_tuple_of_bool_and_str(self):
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = semantic_equivalence_check("text a", "text b")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


# ---------------------------------------------------------------------------
# apply_error_severity_rewrites tests
# ---------------------------------------------------------------------------


class TestApplyErrorSeverityRewrites:
    def test_error_severity_finding_is_applied_when_equivalent(self, tmp_path):
        finding = _make_finding(severity="E")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = apply_error_severity_rewrites(
                feature_id="feat-ac-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1
        assert result["repairs_applied"][0]["smell_id"] == "S09"

    def test_error_severity_finding_not_applied_when_not_equivalent(self, tmp_path):
        finding = _make_finding(severity="E")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(False)):
            result = apply_error_severity_rewrites(
                feature_id="feat-ac-002",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_warning_severity_finding_not_applied(self, tmp_path):
        finding = _make_finding(severity="W")
        result = apply_error_severity_rewrites(
            feature_id="feat-ac-003",
            findings=[finding],
            original_acs=["The system should process requests."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_auto_repair_false_skips_all_repairs(self, tmp_path):
        finding = _make_finding(severity="E")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = apply_error_severity_rewrites(
                feature_id="feat-ac-004",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
                auto_repair=False,
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_empty_findings_returns_original_acs(self, tmp_path):
        original = ["AC one.", "AC two."]
        result = apply_error_severity_rewrites(
            feature_id="feat-ac-005",
            findings=[],
            original_acs=original,
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == original
        assert result["repairs_applied"] == []

    def test_non_string_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id=999,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_findings_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id="feat-ac-006",
                findings="bad",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_repair_log_written_after_apply(self, tmp_path):
        finding = _make_finding(severity="E")
        log_path = tmp_path / "repairs.log"
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            apply_error_severity_rewrites(
                feature_id="feat-ac-007",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=log_path,
            )
        assert log_path.exists()
        content = log_path.read_text()
        assert "feat-ac-007" in content

    def test_finding_without_suggested_rewrite_is_skipped(self, tmp_path):
        finding = {
            "smell_id": "S01",
            "smell_name": "Vague",
            "severity": "E",
            "text": "The system shall be fast.",
            "detail": "No metric.",
            "suggested_rewrite": None,
        }
        result = apply_error_severity_rewrites(
            feature_id="feat-ac-008",
            findings=[finding],
            original_acs=["The system shall be fast."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system shall be fast."]
        assert result["repairs_applied"] == []


# ---------------------------------------------------------------------------
# Module-level checks
# ---------------------------------------------------------------------------


def test_module_has_semantic_equivalence_check():
    assert callable(auto_repair_ac.semantic_equivalence_check)


def test_module_has_apply_error_severity_rewrites():
    assert callable(auto_repair_ac.apply_error_severity_rewrites)
