"""Tests for src/auto_repair.py — semantic_equivalence_check and apply_error_severity_rewrites."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import auto_repair
from auto_repair import semantic_equivalence_check, apply_error_severity_rewrites


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
    def test_returns_true_and_rationale_when_equivalent(self):
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

    def test_returns_false_on_llm_failure(self):
        with patch("auto_repair._call_llm_judge", side_effect=Exception("LLM down")):
            result, rationale = semantic_equivalence_check("original", "rewrite")
        assert result is False
        assert "LLM" in rationale or "fail" in rationale.lower() or len(rationale) > 0

    def test_returns_false_on_unparseable_response(self):
        resp = MagicMock()
        resp.content = [MagicMock(text="I cannot determine equivalence.")]
        with patch("auto_repair._call_llm_judge", return_value=resp):
            result, rationale = semantic_equivalence_check("original", "rewrite")
        assert result is False

    def test_returns_tuple_of_bool_and_str(self):
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = semantic_equivalence_check("a", "b")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


# ---------------------------------------------------------------------------
# apply_error_severity_rewrites tests
# ---------------------------------------------------------------------------


class TestApplyErrorSeverityRewrites:
    def test_applies_error_severity_with_equivalence(self, tmp_path):
        finding = _make_finding(severity="E")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = apply_error_severity_rewrites(
                feature_id="feat-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1

    def test_skips_warn_severity(self, tmp_path):
        finding = _make_finding(severity="W")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = apply_error_severity_rewrites(
                feature_id="feat-002",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_skips_non_equivalent_rewrite(self, tmp_path):
        finding = _make_finding(severity="E")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(False)):
            result = apply_error_severity_rewrites(
                feature_id="feat-003",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_skips_finding_without_suggested_rewrite(self, tmp_path):
        finding = _make_finding(severity="E")
        finding["suggested_rewrite"] = None
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = apply_error_severity_rewrites(
                feature_id="feat-004",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repairs_applied"] == []

    def test_logs_repair_to_file(self, tmp_path):
        finding = _make_finding(severity="E")
        log_file = tmp_path / "repairs.log"
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            apply_error_severity_rewrites(
                feature_id="feat-005",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=log_file,
            )
        assert log_file.exists()
        content = log_file.read_text()
        assert "feat-005" in content

    def test_returns_dict_with_expected_keys(self, tmp_path):
        result = apply_error_severity_rewrites(
            feature_id="feat-006",
            findings=[],
            original_acs=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert "repaired_acs" in result
        assert "repairs_applied" in result

    def test_respects_auto_repair_false(self, tmp_path):
        finding = _make_finding(severity="E")
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result = apply_error_severity_rewrites(
                feature_id="feat-007",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
                auto_repair=False,
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []
