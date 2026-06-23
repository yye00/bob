"""Boundary tests for auto_repair — empty, zero, or minimum input returns well-defined results."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from auto_repair import semantic_equivalence_check, apply_error_severity_rewrites


class TestSemanticEquivalenceCheckBoundary:
    def test_empty_strings_return_false(self):
        with patch("auto_repair._call_llm_judge", side_effect=Exception("empty")):
            result, rationale = semantic_equivalence_check("", "")
        assert result is False
        assert isinstance(rationale, str)

    def test_single_char_strings_do_not_raise(self):
        resp_mock = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        resp_mock.content = [__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(
            text="EQUIVALENT: true\nRATIONALE: Same."
        )]
        with patch("auto_repair._call_llm_judge", return_value=resp_mock):
            result, rationale = semantic_equivalence_check("a", "a")
        assert isinstance(result, bool)
        assert isinstance(rationale, str)

    def test_identical_strings_does_not_raise(self):
        resp_mock = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        resp_mock.content = [__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(
            text="EQUIVALENT: true\nRATIONALE: Identical."
        )]
        with patch("auto_repair._call_llm_judge", return_value=resp_mock):
            result, rationale = semantic_equivalence_check("same text", "same text")
        assert isinstance(result, bool)


class TestApplyErrorSeverityRewritesBoundary:
    def test_empty_findings_returns_empty_repairs(self, tmp_path):
        result = apply_error_severity_rewrites(
            feature_id="feat-boundary-001",
            findings=[],
            original_acs=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == []
        assert result["repairs_applied"] == []

    def test_empty_acs_with_findings_does_not_raise(self, tmp_path):
        finding = {
            "smell_id": "S09",
            "smell_name": "Shall-vs-Should",
            "severity": "E",
            "text": "The system should process requests.",
            "detail": "Uses 'should'.",
            "suggested_rewrite": "The system shall process requests.",
        }
        resp_mock = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        resp_mock.content = [__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(
            text="EQUIVALENT: true\nRATIONALE: OK."
        )]
        with patch("auto_repair._call_llm_judge", return_value=resp_mock):
            result = apply_error_severity_rewrites(
                feature_id="feat-boundary-002",
                findings=[finding],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == []
        assert isinstance(result["repairs_applied"], list)

    def test_single_ac_with_no_smells_passes_through(self, tmp_path):
        result = apply_error_severity_rewrites(
            feature_id="feat-boundary-003",
            findings=[],
            original_acs=["pytest: tests/test_foo.py"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py"]
        assert result["repairs_applied"] == []

    def test_zero_error_severity_findings_among_many(self, tmp_path):
        findings = [
            {
                "smell_id": "S02",
                "smell_name": "VagueQualifier",
                "severity": "W",
                "text": "The system shall respond quickly.",
                "detail": "Vague.",
                "suggested_rewrite": "The system shall respond within 200ms.",
            }
        ]
        result = apply_error_severity_rewrites(
            feature_id="feat-boundary-004",
            findings=findings,
            original_acs=["The system shall respond quickly."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system shall respond quickly."]
