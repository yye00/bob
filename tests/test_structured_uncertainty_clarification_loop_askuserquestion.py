"""Tests for structured_uncertainty_clarification_loop_askuserquestion.

Feature: 5d937499-7d90-44ac-a67b-0aacd0d3c020
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob3.structured_uncertainty_clarification_loop_askuserquestion import (
    structured_uncertainty_clarification_loop_askuserquestion,
)


class TestStructuredUncertaintyClarificationLoopAskUserQuestion:
    """Core tests for the structured_uncertainty_clarification_loop_askuserquestion function."""

    _FUNCS_AC = [
        "File exists: src/bob3/structured_uncertainty_clarification_loop_askuserquestion.py",
        "Function defined: bob3.structured_uncertainty_clarification_loop_askuserquestion.structured_uncertainty_clarification_loop_askuserquestion",
    ]

    def test_structured_uncertainty_clarification_loop_askuserquestion(self):
        """Primary AC test: function executes and returns a dict."""
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=self._FUNCS_AC,
            ci_mode=True,
        )
        assert isinstance(result, dict)

    def test_returns_dict_with_required_keys(self):
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=self._FUNCS_AC,
            ci_mode=True,
        )
        assert "spec_slots" in result
        assert "outcome" in result
        assert "stubs" in result
        assert "uncertain_slots" in result

    def test_ci_mode_with_uncertain_slots_returns_spec_needs_human(self):
        # Use function-defined ACs to generate uncertain slots
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
            "Function defined: bob3.spec_quality.clarification_loop.compute_slot_uncertainty",
            "Function defined: bob3.spec_quality.clarification_loop.ask_user_batched",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            ci_mode=True,
        )
        if result["uncertain_slots"]:
            assert result["outcome"] == "SPEC_NEEDS_HUMAN"

    def test_ci_mode_empty_acs_returns_none_outcome(self):
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=[],
            ci_mode=True,
        )
        assert result["outcome"] is None
        assert result["spec_slots"] == {}

    def test_non_ci_mode_does_not_return_spec_needs_human(self):
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=self._FUNCS_AC,
            ci_mode=False,
        )
        assert result["outcome"] != "SPEC_NEEDS_HUMAN"

    def test_stubs_are_generated(self):
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            ci_mode=True,
        )
        assert isinstance(result["stubs"], list)
        assert len(result["stubs"]) > 0

    def test_n_stubs_parameter_respected(self):
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            n_stubs=2,
            ci_mode=True,
        )
        assert len(result["stubs"]) == 2

    def test_uncertain_slots_above_threshold(self):
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
            "Function defined: bob3.spec_quality.clarification_loop.compute_slot_uncertainty",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            ci_mode=True,
        )
        for slot in result["uncertain_slots"]:
            assert slot["uncertainty_score"] > 0.4

    def test_file_exists_ac_produces_no_stubs(self):
        acs = ["File exists: src/bob3/some_module.py"]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            ci_mode=True,
        )
        assert result["stubs"] == []
        assert result["uncertain_slots"] == []

    def test_uncertain_slots_have_provenance(self):
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            ci_mode=True,
        )
        for slot in result["uncertain_slots"]:
            assert "provenance" in slot
            assert slot["provenance"].startswith("F-R7-")

    def test_uncertain_slots_have_candidates(self):
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
            ci_mode=True,
        )
        for slot in result["uncertain_slots"]:
            assert "candidates" in slot
            assert isinstance(slot["candidates"], list)

    def test_spec_slots_is_dict(self):
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=self._FUNCS_AC,
            ci_mode=True,
        )
        assert isinstance(result["spec_slots"], dict)

    def test_ci_mode_env_var_truthy(self, monkeypatch):
        monkeypatch.setenv("BOB3_CI_MODE", "1")
        acs = [
            "Function defined: bob3.spec_quality.clarification_loop.code_consistency_check",
        ]
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=acs,
        )
        if result["uncertain_slots"]:
            assert result["outcome"] == "SPEC_NEEDS_HUMAN"

    def test_ci_mode_env_var_falsy(self, monkeypatch):
        monkeypatch.setenv("BOB3_CI_MODE", "0")
        result = structured_uncertainty_clarification_loop_askuserquestion(
            acceptance_criteria=self._FUNCS_AC,
        )
        assert result["outcome"] != "SPEC_NEEDS_HUMAN"
