"""Tests for bob.structured_uncertainty_clarification.

Feature: 9a33a8bb-7cc6-4298-b762-3e02b07a1900
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob.structured_uncertainty_clarification import (
    generate_candidate_implementations,
    generate_candidate_stubs,
    detect_ambiguous_slots,
    mark_ambiguous_slots,
    run_clarification_loop,
    trigger_user_question,
)
from spec_synthesis import CandidateStub, DisagreementSlot, SpecNeedsHumanError


class TestGenerateCandidateImplementations:
    def test_returns_list(self):
        acs = ["Function defined: bob.structured_uncertainty_clarification.generate_candidate_implementations"]
        result = generate_candidate_implementations(acs)
        assert isinstance(result, list)

    def test_empty_list_returns_empty(self):
        result = generate_candidate_implementations([])
        assert result == []

    def test_non_function_ac_returns_empty(self):
        result = generate_candidate_implementations(["File exists: src/bob/foo.py"])
        assert result == []

    def test_produces_n_candidates_stubs(self):
        acs = ["Function defined: bob.structured_uncertainty_clarification.generate_candidate_implementations"]
        result = generate_candidate_implementations(acs, n_candidates=3)
        assert len(result) == 3

    def test_n_candidates_two(self):
        acs = ["Function defined: bob.foo.bar"]
        result = generate_candidate_implementations(acs, n_candidates=2)
        assert len(result) == 2

    def test_stub_has_slot_name(self):
        acs = ["Function defined: bob.foo.my_func"]
        result = generate_candidate_implementations(acs)
        assert all(s.slot_name == "my_func" for s in result)

    def test_invalid_type_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_implementations("not a list")  # type: ignore[arg-type]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_implementations(None)  # type: ignore[arg-type]

    def test_non_string_items_raise_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_implementations([123])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_implementations(["Function defined: foo.bar"], n_candidates=0)

    def test_n_candidates_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_implementations(["Function defined: foo.bar"], n_candidates=-1)

    def test_stubs_have_return_type(self):
        acs = ["Function defined: bob.foo.check_it"]
        result = generate_candidate_implementations(acs)
        assert all(isinstance(s.return_type, str) for s in result)

    def test_stubs_have_raised_exceptions(self):
        acs = ["Function defined: bob.foo.check_it"]
        result = generate_candidate_implementations(acs)
        assert all(isinstance(s.raised_exceptions, list) for s in result)


class TestMarkAmbiguousSlots:
    def test_empty_stubs_returns_empty(self):
        result = mark_ambiguous_slots([])
        assert result == []

    def test_identical_stubs_no_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        result = mark_ambiguous_slots(stubs)
        assert result == []

    def test_disagreeing_stubs_marked_ambiguous(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = mark_ambiguous_slots(stubs)
        assert any(s.slot_name == "foo" and s.dimension == "return_type" for s in result)

    def test_invalid_stubs_type_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            mark_ambiguous_slots("not a list")  # type: ignore[arg-type]

    def test_threshold_below_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            mark_ambiguous_slots([], threshold=-0.1)

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            mark_ambiguous_slots([], threshold=1.1)

    def test_threshold_zero_includes_any_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = mark_ambiguous_slots(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    def test_threshold_one_returns_empty(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = mark_ambiguous_slots(stubs, threshold=1.0)
        assert result == []

    def test_result_sorted_by_slot_and_dimension(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = mark_ambiguous_slots(stubs, threshold=0.0)
        names = [(s.slot_name, s.dimension) for s in result]
        assert names == sorted(names)

    def test_uncertainty_score_above_threshold(self):
        stubs = [
            CandidateStub("bar", "bool", [], [], "def bar(): ..."),
            CandidateStub("bar", "int", [], [], "def bar(): ..."),
            CandidateStub("bar", "str", [], [], "def bar(): ..."),
        ]
        result = mark_ambiguous_slots(stubs)
        for slot in result:
            assert slot.uncertainty_score > 0.4

    def test_result_has_candidates_field(self):
        stubs = [
            CandidateStub("baz", "bool", [], [], "def baz(): ..."),
            CandidateStub("baz", "int", [], [], "def baz(): ..."),
            CandidateStub("baz", "str", [], [], "def baz(): ..."),
        ]
        result = mark_ambiguous_slots(stubs, threshold=0.0)
        for slot in result:
            assert isinstance(slot.candidates, list)
            assert len(slot.candidates) >= 1


class TestTriggerUserQuestion:
    def test_empty_slots_returns_empty(self):
        result = trigger_user_question([])
        assert result == []

    def test_empty_slots_ci_mode_returns_empty(self):
        result = trigger_user_question([], ci_mode=True)
        assert result == []

    def test_ci_mode_with_slots_raises_spec_needs_human(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError):
            trigger_user_question([slot], ci_mode=True)

    def test_ci_mode_error_contains_spec_needs_human(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            trigger_user_question([slot], ci_mode=True)

    def test_invalid_slots_type_raises_value_error(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            trigger_user_question("not a list")  # type: ignore[arg-type]

    def test_none_slots_raises_value_error(self):
        with pytest.raises(ValueError):
            trigger_user_question(None)  # type: ignore[arg-type]

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_question([], max_per_round=0)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_question([], max_per_round=6)

    def test_max_per_round_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_question([], max_per_round=-1)

    def test_ci_mode_does_not_silently_succeed_with_slots(self):
        slot = DisagreementSlot(
            slot_name="risky_func",
            provenance="F-R7-999",
            uncertainty_score=0.8,
            candidates=["A", "B"],
            dimension="return_type",
        )
        raised = False
        try:
            trigger_user_question([slot], ci_mode=True)
        except SpecNeedsHumanError:
            raised = True
        assert raised, "Expected SpecNeedsHumanError but no exception was raised"


class TestGenerateCandidateStubs:
    def test_returns_list(self):
        acs = ["Function defined: bob.foo.bar"]
        result = generate_candidate_stubs(acs)
        assert isinstance(result, list)

    def test_empty_list_returns_empty(self):
        assert generate_candidate_stubs([]) == []

    def test_produces_n_candidates(self):
        result = generate_candidate_stubs(["Function defined: bob.foo.bar"], n_candidates=3)
        assert len(result) == 3

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_stubs("not a list")  # type: ignore[arg-type]

    def test_non_string_items_raise_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([123])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(["Function defined: foo.bar"], n_candidates=0)


class TestDetectAmbiguousSlots:
    def test_empty_returns_empty(self):
        assert detect_ambiguous_slots([]) == []

    def test_identical_stubs_no_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        assert detect_ambiguous_slots(stubs) == []

    def test_disagreeing_stubs_detected(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = detect_ambiguous_slots(stubs)
        assert any(s.slot_name == "foo" and s.dimension == "return_type" for s in result)

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            detect_ambiguous_slots("not a list")  # type: ignore[arg-type]

    def test_threshold_out_of_range_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            detect_ambiguous_slots([], threshold=1.5)


class TestRunClarificationLoop:
    def test_empty_acs_returns_no_needs_human(self):
        spec_slots, outcome = run_clarification_loop([])
        assert isinstance(spec_slots, dict)
        assert outcome is None

    def test_ci_mode_ambiguous_returns_spec_needs_human(self):
        spec_slots, outcome = run_clarification_loop(
            ["Function defined: foo.bar"], ci_mode=True
        )
        assert outcome == "SPEC_NEEDS_HUMAN"

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            run_clarification_loop("not a list")  # type: ignore[arg-type]

    def test_non_string_items_raise_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            run_clarification_loop([123])  # type: ignore[arg-type]
