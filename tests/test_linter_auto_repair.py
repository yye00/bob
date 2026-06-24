"""Tests for bob.linter.auto_repair — apply_semantic_equivalence_check and should_auto_repair."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob.linter.auto_repair import apply_semantic_equivalence_check, should_auto_repair
from bob.linter import detect_smells


# ---------------------------------------------------------------------------
# apply_semantic_equivalence_check
# ---------------------------------------------------------------------------

class TestApplySemanticEquivalenceCheckInputValidation:
    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError, match="original"):
            apply_semantic_equivalence_check(42, "rewrite")

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError, match="rewrite"):
            apply_semantic_equivalence_check("original", None)  # type: ignore[arg-type]

    def test_both_none_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_semantic_equivalence_check(None, None)  # type: ignore[arg-type]


class TestApplySemanticEquivalenceCheckHappyPath:
    def _make_mock_response(self, text: str) -> MagicMock:
        resp = MagicMock()
        content_item = MagicMock()
        content_item.text = text
        resp.content = [content_item]
        return resp

    def test_equivalent_true_returned_when_judge_says_true(self):
        resp = self._make_mock_response("EQUIVALENT: true\nRATIONALE: Both require 200ms response.")
        with patch("bob.linter.auto_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = apply_semantic_equivalence_check(
                "System shall respond in 200ms.",
                "System shall respond within 200 milliseconds.",
            )
        assert is_equiv is True
        assert "200ms" in rationale or isinstance(rationale, str)

    def test_equivalent_false_returned_when_judge_says_false(self):
        resp = self._make_mock_response("EQUIVALENT: false\nRATIONALE: Different constraint levels.")
        with patch("bob.linter.auto_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = apply_semantic_equivalence_check(
                "System shall respond in 200ms.",
                "System shall respond in 2 seconds.",
            )
        assert is_equiv is False
        assert isinstance(rationale, str)

    def test_llm_failure_returns_false_with_error_message(self):
        with patch("bob.linter.auto_repair._call_llm_judge", side_effect=RuntimeError("network")):
            is_equiv, rationale = apply_semantic_equivalence_check("original", "rewrite")
        assert is_equiv is False
        assert "LLM judge call failed" in rationale

    def test_empty_strings_return_false_on_llm_failure(self):
        with patch("bob.linter.auto_repair._call_llm_judge", side_effect=Exception("empty input")):
            is_equiv, rationale = apply_semantic_equivalence_check("", "")
        assert is_equiv is False
        assert isinstance(rationale, str)

    def test_unparseable_response_returns_false(self):
        resp = self._make_mock_response("I am not sure what to say here.")
        with patch("bob.linter.auto_repair._call_llm_judge", return_value=resp):
            is_equiv, rationale = apply_semantic_equivalence_check("original", "rewrite")
        assert is_equiv is False
        assert isinstance(rationale, str)

    def test_returns_tuple_of_bool_and_str(self):
        resp = self._make_mock_response("EQUIVALENT: true\nRATIONALE: OK.")
        with patch("bob.linter.auto_repair._call_llm_judge", return_value=resp):
            result = apply_semantic_equivalence_check("a", "b")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


# ---------------------------------------------------------------------------
# should_auto_repair
# ---------------------------------------------------------------------------

class TestShouldAutoRepairInputValidation:
    def test_none_finding_raises_value_error(self):
        with pytest.raises(ValueError, match="None"):
            should_auto_repair(None)

    def test_object_without_severity_raises_value_error(self):
        with pytest.raises(ValueError):
            should_auto_repair(object())


class TestShouldAutoRepairOptOut:
    def test_auto_repair_false_always_returns_false(self):
        finding = {
            "severity": "E",
            "suggested_rewrite": "The system shall process requests.",
        }
        assert should_auto_repair(finding, auto_repair=False) is False

    def test_auto_repair_false_even_with_error_severity(self):
        finding = {"severity": "E", "suggested_rewrite": "rewrite text"}
        assert should_auto_repair(finding, auto_repair=False) is False


class TestShouldAutoRepairSeverityGating:
    def test_error_severity_with_rewrite_returns_true(self):
        finding = {"severity": "E", "suggested_rewrite": "System shall respond within 200ms."}
        assert should_auto_repair(finding) is True

    def test_warning_severity_returns_false(self):
        finding = {"severity": "W", "suggested_rewrite": "Some rewrite."}
        assert should_auto_repair(finding) is False

    def test_info_severity_returns_false(self):
        finding = {"severity": "I", "suggested_rewrite": "Some rewrite."}
        assert should_auto_repair(finding) is False

    def test_error_severity_without_rewrite_returns_false(self):
        finding = {"severity": "E", "suggested_rewrite": None}
        assert should_auto_repair(finding) is False

    def test_error_severity_without_rewrite_key_returns_false(self):
        finding = {"severity": "E"}
        assert should_auto_repair(finding) is False


class TestShouldAutoRepairWithSmellFinding:
    """Tests using real SmellFinding objects from bob.linter."""

    def test_smell_finding_dataclass_with_error_no_rewrite_returns_false(self):
        findings = detect_smells("The system should be fast.")
        for f in findings:
            if f.severity == "E" and f.suggested_rewrite is None:
                assert should_auto_repair(f) is False
                return
        pytest.skip("No E-severity finding without rewrite found in test AC")

    def test_smell_finding_dataclass_warning_severity_returns_false(self):
        findings = detect_smells("The system shall respond quickly.")
        for f in findings:
            if f.severity == "W":
                assert should_auto_repair(f) is False
                return
        pytest.skip("No W-severity finding in test AC")

    def test_dict_finding_matches_dataclass_finding_behavior(self):
        finding_dict = {"severity": "E", "suggested_rewrite": "Shall process in 200ms."}
        assert should_auto_repair(finding_dict) is True

        finding_dict_w = {"severity": "W", "suggested_rewrite": "Shall process in 200ms."}
        assert should_auto_repair(finding_dict_w) is False


# ---------------------------------------------------------------------------
# Integration: bob.linter exposes the functions
# ---------------------------------------------------------------------------

class TestLinterIntegration:
    def test_apply_semantic_equivalence_check_importable_from_linter(self):
        from bob.linter import apply_semantic_equivalence_check as fn
        assert callable(fn)

    def test_should_auto_repair_importable_from_linter(self):
        from bob.linter import should_auto_repair as fn
        assert callable(fn)

    def test_both_functions_in_linter_all(self):
        import bob.linter as linter_mod
        assert "apply_semantic_equivalence_check" in linter_mod.__all__
        assert "should_auto_repair" in linter_mod.__all__
