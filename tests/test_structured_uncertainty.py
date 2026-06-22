"""Tests for bob3.structured_uncertainty.

Feature: 7ceaf559-1ab3-4e3b-84ab-d45e260e6848
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob3.structured_uncertainty import (
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    clarify_ambiguous_slots,
    generate_candidate_implementations,
)
from spec_synthesis import CandidateStub


# ---------------------------------------------------------------------------
# generate_candidate_implementations
# ---------------------------------------------------------------------------


class TestGenerateCandidateImplementations:
    def test_returns_list_for_function_ac(self):
        acs = ["Function defined: bob3.structured_uncertainty.clarify_ambiguous_slots"]
        result = generate_candidate_implementations(acs)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_returns_n_candidates_per_slot(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_implementations(acs, n_candidates=3)
        assert len(result) == 3

    def test_custom_n_candidates_respected(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_implementations(acs, n_candidates=2)
        assert len(result) == 2

    def test_empty_acs_returns_empty_list(self):
        result = generate_candidate_implementations([])
        assert result == []

    def test_file_exists_ac_produces_no_stubs(self):
        acs = ["File exists: src/bob3/structured_uncertainty.py"]
        result = generate_candidate_implementations(acs)
        assert result == []

    def test_returns_candidate_stub_objects(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_implementations(acs)
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_stub_slot_name_matches_function(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_implementations(acs)
        assert all(s.slot_name == "my_func" for s in result)

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_implementations("not a list")  # type: ignore[arg-type]

    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_implementations(None)  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_implementations([123])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_implementations([], n_candidates=0)

    def test_n_candidates_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_implementations([], n_candidates=-5)


# ---------------------------------------------------------------------------
# clarify_ambiguous_slots
# ---------------------------------------------------------------------------


class TestClarifyAmbiguousSlots:
    _FUNC_AC = ["Function defined: bob3.structured_uncertainty.clarify_ambiguous_slots"]

    def test_returns_dict(self):
        result = clarify_ambiguous_slots([], ci_mode=True)
        assert isinstance(result, dict)

    def test_dict_has_required_keys(self):
        result = clarify_ambiguous_slots([], ci_mode=True)
        assert "spec_slots" in result
        assert "outcome" in result
        assert "stubs" in result
        assert "uncertain_slots" in result
        assert "uncertainty_threshold" in result

    def test_empty_acs_returns_none_outcome(self):
        result = clarify_ambiguous_slots([], ci_mode=True)
        assert result["outcome"] is None
        assert result["spec_slots"] == {}
        assert result["stubs"] == []
        assert result["uncertain_slots"] == []

    def test_threshold_in_result_matches_default(self):
        result = clarify_ambiguous_slots([], ci_mode=True)
        assert result["uncertainty_threshold"] == UNCERTAINTY_THRESHOLD

    def test_custom_threshold_reflected_in_result(self):
        result = clarify_ambiguous_slots([], ci_mode=True, threshold=0.6)
        assert result["uncertainty_threshold"] == 0.6

    def test_ci_mode_with_uncertain_slots_returns_spec_needs_human(self):
        acs = [
            "Function defined: bob3.structured_uncertainty.clarify_ambiguous_slots",
            "Function defined: bob3.structured_uncertainty.generate_candidate_implementations",
        ]
        result = clarify_ambiguous_slots(acs, ci_mode=True)
        if result["uncertain_slots"]:
            assert result["outcome"] == SPEC_NEEDS_HUMAN
            assert result["spec_slots"] == {}

    def test_non_ci_mode_does_not_return_spec_needs_human(self):
        result = clarify_ambiguous_slots(self._FUNC_AC, ci_mode=False)
        assert result["outcome"] != SPEC_NEEDS_HUMAN

    def test_stubs_are_list(self):
        result = clarify_ambiguous_slots(self._FUNC_AC, ci_mode=True)
        assert isinstance(result["stubs"], list)

    def test_stubs_have_required_fields(self):
        result = clarify_ambiguous_slots(self._FUNC_AC, ci_mode=True)
        for stub in result["stubs"]:
            assert "slot_name" in stub
            assert "return_type" in stub
            assert "raised_exceptions" in stub
            assert "side_effects" in stub
            assert "raw_stub" in stub

    def test_uncertain_slots_are_list(self):
        result = clarify_ambiguous_slots(self._FUNC_AC, ci_mode=True)
        assert isinstance(result["uncertain_slots"], list)

    def test_uncertain_slots_have_required_fields(self):
        result = clarify_ambiguous_slots(self._FUNC_AC, ci_mode=True)
        for slot in result["uncertain_slots"]:
            assert "slot_name" in slot
            assert "provenance" in slot
            assert "uncertainty_score" in slot
            assert "candidates" in slot
            assert "dimension" in slot

    def test_uncertain_slots_above_threshold(self):
        result = clarify_ambiguous_slots(self._FUNC_AC, ci_mode=True)
        for slot in result["uncertain_slots"]:
            assert slot["uncertainty_score"] > UNCERTAINTY_THRESHOLD

    def test_spec_slots_is_dict(self):
        result = clarify_ambiguous_slots([], ci_mode=True)
        assert isinstance(result["spec_slots"], dict)

    def test_file_exists_ac_produces_no_stubs(self):
        acs = ["File exists: src/bob3/structured_uncertainty.py"]
        result = clarify_ambiguous_slots(acs, ci_mode=True)
        assert result["stubs"] == []
        assert result["uncertain_slots"] == []
        assert result["outcome"] is None

    def test_ci_mode_env_var_truthy(self, monkeypatch):
        monkeypatch.setenv("BOB3_CI_MODE", "1")
        result = clarify_ambiguous_slots(self._FUNC_AC)
        if result["uncertain_slots"]:
            assert result["outcome"] == SPEC_NEEDS_HUMAN

    def test_non_list_acs_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            clarify_ambiguous_slots("not a list")  # type: ignore[arg-type]

    def test_none_acs_raises_value_error(self):
        with pytest.raises(ValueError):
            clarify_ambiguous_slots(None)  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises(ValueError):
            clarify_ambiguous_slots([123], ci_mode=True)  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates"):
            clarify_ambiguous_slots([], n_candidates=0, ci_mode=True)

    def test_threshold_below_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            clarify_ambiguous_slots([], threshold=-0.1, ci_mode=True)

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            clarify_ambiguous_slots([], threshold=1.1, ci_mode=True)

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            clarify_ambiguous_slots([], max_per_round=0, ci_mode=True)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            clarify_ambiguous_slots([], max_per_round=6, ci_mode=True)
