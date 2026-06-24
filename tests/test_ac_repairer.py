"""Tests for bob.ac_repairer — repair_smelly_acs and verify_semantic_equivalence."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.ac_repairer import repair_smelly_acs, verify_semantic_equivalence


class TestVerifySemanticEquivalence:
    def test_returns_true_when_judge_says_equivalent(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: Identical meaning.")]
        with patch("bob.ac_repairer._call_llm_judge", return_value=mock_response):
            is_equiv, rationale = verify_semantic_equivalence(
                "The system shall respond within 200ms.",
                "The system must respond within 200ms.",
            )
        assert is_equiv is True
        assert "Identical meaning" in rationale

    def test_returns_false_when_judge_says_not_equivalent(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="EQUIVALENT: false\nRATIONALE: Different meaning.")]
        with patch("bob.ac_repairer._call_llm_judge", return_value=mock_response):
            is_equiv, rationale = verify_semantic_equivalence(
                "The system shall respond within 200ms.",
                "The system shall respond within 500ms.",
            )
        assert is_equiv is False

    def test_raises_value_error_for_non_string_original(self):
        with pytest.raises(ValueError, match="original must be a string"):
            verify_semantic_equivalence(123, "rewrite")  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_rewrite(self):
        with pytest.raises(ValueError, match="rewrite must be a string"):
            verify_semantic_equivalence("original", None)  # type: ignore[arg-type]

    def test_returns_false_on_llm_failure(self):
        with patch("bob.ac_repairer._call_llm_judge", side_effect=Exception("timeout")):
            is_equiv, rationale = verify_semantic_equivalence("orig", "rewrite")
        assert is_equiv is False
        assert "timeout" in rationale

    def test_returns_false_on_empty_response(self):
        mock_response = MagicMock()
        mock_response.content = []
        with patch("bob.ac_repairer._call_llm_judge", return_value=mock_response):
            is_equiv, rationale = verify_semantic_equivalence("original", "rewrite")
        assert is_equiv is False


class TestRepairSmellAcs:
    def test_clean_acs_pass_through_unchanged(self, tmp_path):
        result = repair_smelly_acs(
            feature_id="feat-001",
            acceptance_criteria=["pytest: tests/test_foo.py -v"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert "pytest: tests/test_foo.py -v" in result["repaired_acs"]
        assert result["auto_repair_enabled"] is True

    def test_opt_out_prevents_repairs(self, tmp_path):
        result = repair_smelly_acs(
            feature_id="feat-opt-out",
            acceptance_criteria=["The system should process requests."],
            auto_repair=False,
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["auto_repair_enabled"] is False
        assert result["repairs_applied"] == []
        assert result["repaired_acs"] == ["The system should process requests."]

    def test_returns_required_keys(self, tmp_path):
        result = repair_smelly_acs(
            feature_id="feat-002",
            acceptance_criteria=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert "repaired_acs" in result
        assert "repairs_applied" in result
        assert "smell_findings" in result
        assert "auto_repair_enabled" in result

    def test_empty_acs_returns_empty_results(self, tmp_path):
        result = repair_smelly_acs(
            feature_id="feat-empty",
            acceptance_criteria=[],
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repaired_acs"] == []
        assert result["repairs_applied"] == []

    def test_raises_value_error_for_non_string_feature_id(self, tmp_path):
        with pytest.raises(ValueError, match="feature_id must be a string"):
            repair_smelly_acs(
                feature_id=None,  # type: ignore[arg-type]
                acceptance_criteria=[],
            )

    def test_raises_value_error_for_non_list_acs(self, tmp_path):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            repair_smelly_acs(
                feature_id="feat-003",
                acceptance_criteria="not a list",  # type: ignore[arg-type]
            )

    def test_smell_findings_is_a_list(self, tmp_path):
        result = repair_smelly_acs(
            feature_id="feat-004",
            acceptance_criteria=["pytest: tests/test_foo.py"],
            repairs_log=tmp_path / "repairs.log",
        )
        assert isinstance(result["smell_findings"], list)

    def test_spec_critic_integration_import(self):
        """Verify the module can be imported from bob.ac_repairer (spec_critic integration)."""
        from bob.ac_repairer import repair_smelly_acs as rsa
        from bob.ac_repairer import verify_semantic_equivalence as vse
        assert callable(rsa)
        assert callable(vse)
