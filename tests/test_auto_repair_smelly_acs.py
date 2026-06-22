"""Tests for src/auto_repair_smelly_acs.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_repair_smelly_acs import verify_semantic_equivalence, apply_error_severity_rewrites


def _mock_llm_equiv(is_equiv: bool) -> MagicMock:
    resp = MagicMock()
    flag = "true" if is_equiv else "false"
    resp.content = [MagicMock(text=f"EQUIVALENT: {flag}\nRATIONALE: Test rationale.")]
    return resp


def _make_finding(severity: str = "E", text: str = "The system should process requests.") -> dict:
    return {
        "smell_id": "S09",
        "smell_name": "Shall-vs-Should",
        "severity": severity,
        "text": text,
        "detail": "Uses 'should' where 'shall' is required.",
        "suggested_rewrite": "The system shall process requests.",
    }


class TestVerifySemanticEquivalence:
    def test_returns_true_when_equivalent(self):
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            result, rationale = verify_semantic_equivalence(
                "The system should process requests.",
                "The system shall process requests.",
            )
        assert result is True
        assert isinstance(rationale, str)

    def test_returns_false_when_not_equivalent(self):
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(False)):
            result, rationale = verify_semantic_equivalence(
                "The system shall process requests.",
                "The system shall reject all requests.",
            )
        assert result is False
        assert isinstance(rationale, str)

    def test_raises_value_error_for_non_string_original(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence(123, "some rewrite")  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_rewrite(self):
        with pytest.raises(ValueError):
            verify_semantic_equivalence("some original", None)  # type: ignore[arg-type]

    def test_returns_false_on_llm_failure(self):
        with patch("auto_repair._call_llm_judge", side_effect=Exception("network error")):
            result, rationale = verify_semantic_equivalence("original", "rewrite")
        assert result is False
        assert "network error" in rationale or isinstance(rationale, str)


class TestApplyErrorSeverityRewrites:
    def test_applies_error_severity_rewrite_when_equivalent(self, tmp_path):
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

    def test_skips_warning_severity_findings(self, tmp_path):
        finding = _make_finding(severity="W")
        result = apply_error_severity_rewrites(
            feature_id="feat-002",
            findings=[finding],
            original_acs=["The system should process requests."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_rejects_non_equivalent_rewrite(self, tmp_path):
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

    def test_opt_out_prevents_repair(self, tmp_path):
        finding = _make_finding(severity="E")
        result = apply_error_severity_rewrites(
            feature_id="feat-004",
            findings=[finding],
            original_acs=["The system should process requests."],
            repairs_log=tmp_path / "repairs.log",
            auto_repair=False,
        )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_empty_inputs_return_empty_results(self, tmp_path):
        result = apply_error_severity_rewrites(
            feature_id="feat-005",
            findings=[],
            original_acs=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == []
        assert result["repairs_applied"] == []

    def test_raises_value_error_for_invalid_feature_id(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id=None,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_invalid_findings(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id="feat-006",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_invalid_original_acs(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id="feat-007",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_repair_logged_to_file(self, tmp_path):
        finding = _make_finding(severity="E")
        log_path = tmp_path / "repairs.log"
        with patch("auto_repair._call_llm_judge", return_value=_mock_llm_equiv(True)):
            apply_error_severity_rewrites(
                feature_id="feat-008",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=log_path,
            )
        assert log_path.exists()
        content = log_path.read_text()
        assert "feat-008" in content
