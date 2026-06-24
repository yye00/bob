"""Tests for spec_synthesis.uncertainty_clarifier.

Feature: 97e073b1-11a2-4388-9f2d-178bc1ce0b7a
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from spec_synthesis.uncertainty_clarifier import (
    generate_candidate_stubs,
    identify_ambiguous_slots,
    trigger_user_clarification,
)
from spec_synthesis import CandidateStub, ClarificationAnswer, DisagreementSlot, SpecNeedsHumanError


_FUNC_ACS = [
    "Function defined: spec_synthesis.uncertainty_clarifier.generate_candidate_stubs",
    "Function defined: spec_synthesis.uncertainty_clarifier.identify_ambiguous_slots",
    "Function defined: spec_synthesis.uncertainty_clarifier.trigger_user_clarification",
]


class TestGenerateCandidateStubs:
    def test_returns_list_of_candidate_stubs(self):
        result = generate_candidate_stubs(_FUNC_ACS)
        assert isinstance(result, list)
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_produces_n_stubs_per_slot(self):
        acs = ["Function defined: mymod.my_func"]
        result = generate_candidate_stubs(acs)
        assert len(result) == 3

    def test_n_candidates_parameter(self):
        acs = ["Function defined: mymod.my_func"]
        result = generate_candidate_stubs(acs, n_candidates=2)
        assert len(result) == 2

    def test_empty_acs_returns_empty(self):
        assert generate_candidate_stubs([]) == []

    def test_non_function_ac_produces_no_stubs(self):
        acs = ["File exists: src/something.py"]
        assert generate_candidate_stubs(acs) == []

    def test_stubs_have_slot_name(self):
        acs = ["Function defined: mymod.compute_score"]
        stubs = generate_candidate_stubs(acs)
        assert all(s.slot_name == "compute_score" for s in stubs)

    def test_stubs_vary_in_return_type(self):
        acs = ["Function defined: mymod.compute_score"]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        return_types = {s.return_type for s in stubs}
        assert len(return_types) > 1

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs("not a list")  # type: ignore[arg-type]

    def test_non_string_item_raises_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([42])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs([], n_candidates=0)


class TestIdentifyAmbiguousSlots:
    def test_returns_list_of_disagreement_slots(self):
        acs = ["Function defined: mymod.compute_score"]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        result = identify_ambiguous_slots(stubs)
        assert isinstance(result, list)
        assert all(isinstance(s, DisagreementSlot) for s in result)

    def test_empty_stubs_returns_empty(self):
        assert identify_ambiguous_slots([]) == []

    def test_identical_stubs_produce_no_ambiguity(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
        ]
        result = identify_ambiguous_slots(stubs)
        assert result == []

    def test_divergent_stubs_produce_ambiguity(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", ["ValueError"], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], ["writes_to_log"], "def foo(): ..."),
        ]
        result = identify_ambiguous_slots(stubs)
        assert len(result) > 0

    def test_threshold_zero_finds_any_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = identify_ambiguous_slots(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    def test_threshold_one_finds_nothing(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = identify_ambiguous_slots(stubs, threshold=1.0)
        assert result == []

    def test_non_list_stubs_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            identify_ambiguous_slots("bad")  # type: ignore[arg-type]

    def test_threshold_below_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            identify_ambiguous_slots([], threshold=-0.1)

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            identify_ambiguous_slots([], threshold=1.1)

    def test_slot_names_in_result(self):
        acs = [
            "Function defined: mymod.check_consistency",
            "Function defined: mymod.compute_score",
        ]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        result = identify_ambiguous_slots(stubs)
        slot_names = {s.slot_name for s in result}
        assert "check_consistency" in slot_names or "compute_score" in slot_names


class TestTriggerUserClarification:
    def test_empty_slots_returns_empty_list(self):
        result = trigger_user_clarification([])
        assert result == []

    def test_empty_slots_ci_mode_returns_empty_list(self):
        result = trigger_user_clarification([], ci_mode=True)
        assert result == []

    def test_ci_mode_with_slots_raises_spec_needs_human(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=1.0,
            candidates=["bool", "int", "str"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError):
            trigger_user_clarification([slot], ci_mode=True)

    def test_ci_mode_error_contains_sentinel(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "None"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            trigger_user_clarification([slot], ci_mode=True)

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            trigger_user_clarification("bad")  # type: ignore[arg-type]

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=0)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=6)

    def test_non_ci_non_tty_auto_selects(self, tmp_path):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=1.0,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        result = trigger_user_clarification(
            [slot],
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert isinstance(result[0], ClarificationAnswer)
        assert result[0].slot_name == "my_func"

    def test_multiple_slots_non_ci_returns_all_answers(self, tmp_path):
        slots = [
            DisagreementSlot("a", "F-R7-451", 1.0, ["bool", "int"], "return_type"),
            DisagreementSlot("b", "F-R7-452", 1.0, ["None", "str"], "return_type"),
        ]
        result = trigger_user_clarification(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 2
