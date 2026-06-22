"""Tests for bob3.ac_smell_rewriter module.

Covers apply_suggested_rewrite and verify_semantic_equivalence.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob3.ac_smell_rewriter import (
    apply_suggested_rewrite,
    verify_semantic_equivalence,
    EquivalenceJudgeUnavailableError,
    RewriteRejectedError,
    SmellFinding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_finding(text: str = "The system should process requests.") -> SmellFinding:
    return SmellFinding(
        smell_id="S09",
        smell_name="Should Instead of Shall",
        severity="E",
        text=text,
        detail="Uses 'should' where 'shall' is required.",
    )


def _warn_finding(text: str = "The system shall respond quickly.") -> SmellFinding:
    return SmellFinding(
        smell_id="S02",
        smell_name="Vague Performance",
        severity="W",
        text=text,
        detail="Vague performance qualifier.",
    )


def _info_finding(text: str = "The system shall process requests.") -> SmellFinding:
    return SmellFinding(
        smell_id="S01",
        smell_name="Info Smell",
        severity="I",
        text=text,
        detail="Informational only.",
    )


def _llm_equiv_true() -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: Same observable constraint.")]
    return resp


def _llm_equiv_false() -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text="EQUIVALENT: false\nRATIONALE: Different meaning.")]
    return resp


def _llm_rewrite(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


# ---------------------------------------------------------------------------
# Tests: verify_semantic_equivalence
# ---------------------------------------------------------------------------

class TestVerifySemanticEquivalence:
    def test_returns_true_when_judge_agrees(self) -> None:
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_true()):
            is_eq, rationale = verify_semantic_equivalence(
                "The system should log errors.",
                "The system shall log errors.",
            )
        assert is_eq is True
        assert "Same observable constraint" in rationale

    def test_returns_false_when_judge_disagrees(self) -> None:
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_false()):
            is_eq, rationale = verify_semantic_equivalence(
                "The system shall log errors.",
                "The system shall not log errors.",
            )
        assert is_eq is False
        assert rationale

    def test_returns_false_on_llm_failure(self) -> None:
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", side_effect=RuntimeError("API error")):
            is_eq, rationale = verify_semantic_equivalence(
                "The system shall log errors.",
                "The system shall log errors (clarified).",
            )
        assert is_eq is False
        assert rationale

    def test_raises_valueerror_on_empty_original(self) -> None:
        with pytest.raises(ValueError, match="original"):
            verify_semantic_equivalence("", "some rewrite")

    def test_raises_valueerror_on_empty_rewrite(self) -> None:
        with pytest.raises(ValueError, match="rewrite"):
            verify_semantic_equivalence("original text", "")

    def test_raises_valueerror_on_whitespace_original(self) -> None:
        with pytest.raises(ValueError, match="original"):
            verify_semantic_equivalence("   ", "some rewrite")

    def test_raises_valueerror_on_whitespace_rewrite(self) -> None:
        with pytest.raises(ValueError, match="rewrite"):
            verify_semantic_equivalence("original text", "   ")


# ---------------------------------------------------------------------------
# Tests: apply_suggested_rewrite
# ---------------------------------------------------------------------------

class TestApplySuggestedRewrite:
    def test_error_severity_applied_when_equivalent(self) -> None:
        finding = _error_finding()
        rewritten = "The system shall process requests."
        with (
            patch("bob3.spec_quality.ac_auto_repair._call_llm_judge") as mock_llm,
        ):
            # First call: rewrite generation. Second call: equivalence check.
            mock_llm.side_effect = [_llm_rewrite(rewritten), _llm_equiv_true()]
            result_text, was_applied = apply_suggested_rewrite(finding, auto_repair=True)
        assert was_applied is True
        assert result_text == rewritten

    def test_error_severity_not_applied_when_not_equivalent(self) -> None:
        finding = _error_finding()
        with (
            patch("bob3.spec_quality.ac_auto_repair._call_llm_judge") as mock_llm,
        ):
            mock_llm.side_effect = [
                _llm_rewrite("The system shall process requests."),
                _llm_equiv_false(),
            ]
            result_text, was_applied = apply_suggested_rewrite(finding, auto_repair=True)
        assert was_applied is False
        assert result_text == finding.text

    def test_warn_severity_not_applied(self) -> None:
        finding = _warn_finding()
        result_text, was_applied = apply_suggested_rewrite(finding, auto_repair=True)
        assert was_applied is False
        assert result_text == finding.text

    def test_info_severity_not_applied(self) -> None:
        finding = _info_finding()
        result_text, was_applied = apply_suggested_rewrite(finding, auto_repair=True)
        assert was_applied is False
        assert result_text == finding.text

    def test_auto_repair_false_skips_repair(self) -> None:
        finding = _error_finding()
        result_text, was_applied = apply_suggested_rewrite(finding, auto_repair=False)
        assert was_applied is False
        assert result_text == finding.text

    def test_raises_valueerror_on_non_finding(self) -> None:
        with pytest.raises(ValueError, match="SmellFinding"):
            apply_suggested_rewrite("not a finding")  # type: ignore[arg-type]

    def test_no_rewrite_available_returns_original(self) -> None:
        finding = SmellFinding(
            smell_id="S09",
            smell_name="Should Instead of Shall",
            severity="E",
            text="The system should process requests.",
            detail="Uses 'should'.",
        )
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", side_effect=RuntimeError("fail")):
            result_text, was_applied = apply_suggested_rewrite(finding, auto_repair=True)
        assert was_applied is False
        assert result_text == finding.text
