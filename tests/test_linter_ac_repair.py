"""Tests for bob3.linter_ac_repair — semantic_equivalence_check and auto_repair_ac."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.linter_ac_repair import auto_repair_ac, semantic_equivalence_check


def _make_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def _make_finding(
    severity: str = "E",
    text: str = "The system should process requests.",
    suggested_rewrite: str | None = "The system shall process requests.",
    smell_id: str = "S09",
    smell_name: str = "Shall-vs-Should",
) -> dict:
    return {
        "smell_id": smell_id,
        "smell_name": smell_name,
        "severity": severity,
        "text": text,
        "detail": "Uses 'should' instead of 'shall'.",
        "suggested_rewrite": suggested_rewrite,
    }


# ---------------------------------------------------------------------------
# semantic_equivalence_check
# ---------------------------------------------------------------------------


class TestSemanticEquivalenceCheck:
    def test_returns_true_when_judge_says_equivalent(self):
        resp = _make_response("EQUIVALENT: true\nRATIONALE: Same constraint.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = semantic_equivalence_check(
                "The system shall process requests.",
                "The system must process requests.",
            )
        assert is_equiv is True
        assert "Same constraint" in rationale

    def test_returns_false_when_judge_says_not_equivalent(self):
        resp = _make_response("EQUIVALENT: false\nRATIONALE: Different semantics.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = semantic_equivalence_check(
                "The system shall respond within 200ms.",
                "The system shall respond within 2s.",
            )
        assert is_equiv is False
        assert isinstance(rationale, str)

    def test_llm_failure_returns_false(self):
        with patch(
            "bob3.linter_ac_repair._call_llm_judge",
            side_effect=RuntimeError("network error"),
        ):
            is_equiv, rationale = semantic_equivalence_check("original", "rewrite")
        assert is_equiv is False
        assert "network error" in rationale or "LLM judge call failed" in rationale

    def test_empty_response_returns_false(self):
        resp = MagicMock()
        resp.content = []
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = semantic_equivalence_check("original", "rewrite")
        assert is_equiv is False

    def test_malformed_response_returns_false(self):
        resp = _make_response("I cannot determine equivalence.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = semantic_equivalence_check("original", "rewrite")
        assert is_equiv is False

    def test_raises_value_error_for_non_string_original(self):
        with pytest.raises(ValueError, match="original"):
            semantic_equivalence_check(42, "rewrite")  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_rewrite(self):
        with pytest.raises(ValueError, match="rewrite"):
            semantic_equivalence_check("original", None)  # type: ignore[arg-type]

    def test_case_insensitive_parsing_true(self):
        resp = _make_response("equivalent: TRUE\nRATIONALE: OK.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, _ = semantic_equivalence_check("a", "b")
        assert is_equiv is True

    def test_case_insensitive_parsing_false(self):
        resp = _make_response("EQUIVALENT: FALSE\nRATIONALE: Nope.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            is_equiv, _ = semantic_equivalence_check("a", "b")
        assert is_equiv is False


# ---------------------------------------------------------------------------
# auto_repair_ac
# ---------------------------------------------------------------------------


class TestAutoRepairAc:
    def test_applies_error_severity_repair_when_equivalent(self, tmp_path):
        finding = _make_finding()
        resp = _make_response("EQUIVALENT: true\nRATIONALE: Same meaning.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-001",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall process requests."]
        assert len(result["repairs_applied"]) == 1
        repair = result["repairs_applied"][0]
        assert repair["feature_id"] == "feat-001"
        assert repair["smell_id"] == "S09"
        assert repair["original"] == "The system should process requests."
        assert repair["rewrite"] == "The system shall process requests."

    def test_does_not_apply_repair_when_not_equivalent(self, tmp_path):
        finding = _make_finding()
        resp = _make_response("EQUIVALENT: false\nRATIONALE: Different semantics.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-002",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system should process requests."]
        assert result["repairs_applied"] == []

    def test_skips_warning_severity_findings(self, tmp_path):
        finding = _make_finding(severity="W")
        resp = _make_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-003",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should process requests."]

    def test_opt_out_prevents_repair(self, tmp_path):
        finding = _make_finding()
        resp = _make_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp) as mock_judge:
            result = auto_repair_ac(
                feature_id="feat-004",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=tmp_path / "repairs.log",
                auto_repair=False,
            )
        mock_judge.assert_not_called()
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should process requests."]

    def test_empty_findings_returns_unchanged_acs(self, tmp_path):
        result = auto_repair_ac(
            feature_id="feat-005",
            findings=[],
            original_acs=["pytest: tests/test_foo.py"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py"]
        assert result["repairs_applied"] == []

    def test_finding_without_suggested_rewrite_is_skipped(self, tmp_path):
        finding = _make_finding(suggested_rewrite=None)
        result = auto_repair_ac(
            feature_id="feat-006",
            findings=[finding],
            original_acs=["The system should process requests."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []

    def test_repair_record_written_to_log(self, tmp_path):
        finding = _make_finding()
        resp = _make_response("EQUIVALENT: true\nRATIONALE: OK.")
        repairs_log = tmp_path / "repairs.log"
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            auto_repair_ac(
                feature_id="feat-007",
                findings=[finding],
                original_acs=["The system should process requests."],
                repairs_log=repairs_log,
            )
        assert repairs_log.exists()
        content = repairs_log.read_text()
        assert "feat-007" in content
        assert "S09" in content

    def test_raises_value_error_for_invalid_feature_id(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id"):
            auto_repair_ac(
                feature_id=None,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_non_list_findings(self, tmp_path):
        with pytest.raises(ValueError, match="findings"):
            auto_repair_ac(
                feature_id="feat-008",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_raises_value_error_for_non_list_acs(self, tmp_path):
        with pytest.raises(ValueError, match="original_acs"):
            auto_repair_ac(
                feature_id="feat-009",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_only_matching_ac_is_repaired(self, tmp_path):
        finding = _make_finding(text="The system should process requests.")
        resp = _make_response("EQUIVALENT: true\nRATIONALE: Same.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-010",
                findings=[finding],
                original_acs=[
                    "pytest: tests/test_foo.py",
                    "The system should process requests.",
                ],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"][0] == "pytest: tests/test_foo.py"
        assert result["repaired_acs"][1] == "The system shall process requests."

    def test_accepts_namedtuple_style_finding(self, tmp_path):
        from collections import namedtuple

        Finding = namedtuple(
            "Finding",
            ["smell_id", "smell_name", "severity", "text", "detail", "suggested_rewrite"],
        )
        finding = Finding(
            smell_id="S09",
            smell_name="Shall-vs-Should",
            severity="E",
            text="The system should log errors.",
            detail="Uses 'should'.",
            suggested_rewrite="The system shall log errors.",
        )
        resp = _make_response("EQUIVALENT: true\nRATIONALE: Same obligation.")
        with patch("bob3.linter_ac_repair._call_llm_judge", return_value=resp):
            result = auto_repair_ac(
                feature_id="feat-011",
                findings=[finding],
                original_acs=["The system should log errors."],
                repairs_log=tmp_path / "repairs.log",
            )
        assert result["repaired_acs"] == ["The system shall log errors."]
        assert len(result["repairs_applied"]) == 1


# ---------------------------------------------------------------------------
# Integration: bob3.linter exports auto_repair_ac and semantic_equivalence_check
# ---------------------------------------------------------------------------


class TestLinterIntegration:
    def test_auto_repair_ac_importable_from_bob3_linter(self):
        from bob3.linter import auto_repair_ac as _auto_repair_ac
        from bob3.linter import semantic_equivalence_check as _sem_check

        assert callable(_auto_repair_ac)
        assert callable(_sem_check)

    def test_auto_repair_ac_from_linter_is_same_function(self):
        from bob3.linter import auto_repair_ac as linter_auto_repair
        from bob3.linter_ac_repair import auto_repair_ac as direct_auto_repair

        assert linter_auto_repair is direct_auto_repair

    def test_semantic_equivalence_check_from_linter_is_same_function(self):
        from bob3.linter import semantic_equivalence_check as linter_sem_check
        from bob3.linter_ac_repair import semantic_equivalence_check as direct_sem_check

        assert linter_sem_check is direct_sem_check
