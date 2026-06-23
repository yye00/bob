"""Tests that the semantic-equivalence judge rejects non-equivalent rewrites."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob3.spec_quality.ac_auto_repair import verify_semantic_equivalence


class TestVerifySemanticEquivalenceRejectsNonEquivalent:
    """verify_semantic_equivalence must return False when the LLM judge says no."""

    def test_returns_false_when_judge_says_not_equivalent(self) -> None:
        judge_response = MagicMock()
        judge_response.content = [MagicMock(text="EQUIVALENT: false\nRATIONALE: The rewrite changes the meaning.")]

        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=judge_response):
            result, rationale = verify_semantic_equivalence(
                original="The system should be fast.",
                rewrite="The system shall respond within 200ms.",
            )
        assert result is False
        assert rationale  # some rationale text returned

    def test_returns_true_when_judge_says_equivalent(self) -> None:
        judge_response = MagicMock()
        judge_response.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: Same observable constraint.")]

        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=judge_response):
            result, rationale = verify_semantic_equivalence(
                original="The system should store user data.",
                rewrite="The system shall persist user data.",
            )
        assert result is True
        assert "Same observable constraint" in rationale

    def test_rejects_when_llm_call_raises(self) -> None:
        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", side_effect=Exception("network error")):
            result, rationale = verify_semantic_equivalence(
                original="The system should process requests.",
                rewrite="The system shall process requests.",
            )
        assert result is False
        assert rationale  # error rationale present

    def test_rejects_ambiguous_judge_response(self) -> None:
        judge_response = MagicMock()
        judge_response.content = [MagicMock(text="I cannot determine equivalence from this context.")]

        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=judge_response):
            result, rationale = verify_semantic_equivalence(
                original="It should work.",
                rewrite="The payment module shall process transactions.",
            )
        assert result is False

    def test_suggest_rewrite_returns_string(self) -> None:
        from bob3.spec_quality.ac_auto_repair import suggest_rewrite
        from bob3.spec_quality.smell_detectors import SmellFinding

        finding = SmellFinding(
            smell_id="S09",
            smell_name="modal-weakness",
            severity="E",
            text="The system should process requests quickly.",
            detail="Uses 'should' where 'shall' is required.",
        )
        judge_response = MagicMock()
        judge_response.content = [MagicMock(text="The system shall process requests.")]

        with patch("bob3.spec_quality.ac_auto_repair._call_llm_judge", return_value=judge_response):
            rewrite = suggest_rewrite(finding)

        assert isinstance(rewrite, str)
        assert len(rewrite) > 0

    def test_suggest_rewrite_info_smell_returns_none_or_string(self) -> None:
        from bob3.spec_quality.ac_auto_repair import suggest_rewrite
        from bob3.spec_quality.smell_detectors import SmellFinding

        finding = SmellFinding(
            smell_id="S15",
            smell_name="tautology",
            severity="I",
            text="The system shall be a system.",
            detail="Restates feature name.",
        )
        rewrite = suggest_rewrite(finding)
        # Info smells: may return None or a string (implementation choice)
        assert rewrite is None or isinstance(rewrite, str)
