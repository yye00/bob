"""Tests for bob.uncertainty_clarification_loop.

Feature: 25705219-4c54-4522-b556-adfad3c72f08
Spec: Structured-uncertainty clarification loop with AskUserQuestion.

Generate N=3 candidate stub implementations from the draft spec; if they
disagree on observable behaviour, mark the relevant slot ambiguous. Slots
above uncertainty threshold T=0.4 trigger a batched (1-5 per round)
multiple-choice question citing provenance. In CI mode with no human
present, exit SPEC_NEEDS_HUMAN rather than confabulate.
"""

from __future__ import annotations

import pytest

from bob.uncertainty_clarification_loop import (
    CandidateStub,
    ClarificationQuestion,
    DisagreementSlot,
    SPEC_NEEDS_HUMAN,
    SpecNeedsHumanError,
    UNCERTAINTY_THRESHOLD,
    build_clarification_questions,
    generate_candidate_stubs,
    mark_ambiguous_slots,
)


_FUNC_AC = "Function defined: bob.uncertainty_clarification_loop.generate_candidate_stubs"


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    def test_returns_n_stubs_per_slot(self):
        stubs = generate_candidate_stubs([_FUNC_AC])
        assert len(stubs) == 3  # default N=3
        assert all(isinstance(s, CandidateStub) for s in stubs)

    def test_slot_name_is_short_function_name(self):
        stubs = generate_candidate_stubs([_FUNC_AC])
        assert all(s.slot_name == "generate_candidate_stubs" for s in stubs)

    def test_custom_n_candidates(self):
        stubs = generate_candidate_stubs([_FUNC_AC], n_candidates=2)
        assert len(stubs) == 2

    def test_non_function_ac_produces_no_stubs(self):
        stubs = generate_candidate_stubs(
            ["File exists: src/bob/uncertainty_clarification_loop.py"]
        )
        assert stubs == []

    def test_multiple_slots(self):
        acs = [
            "Function defined: mod.foo",
            "Function defined: mod.bar",
        ]
        stubs = generate_candidate_stubs(acs)
        assert len(stubs) == 6  # 2 slots × 3 candidates
        assert {s.slot_name for s in stubs} == {"foo", "bar"}


# ---------------------------------------------------------------------------
# mark_ambiguous_slots
# ---------------------------------------------------------------------------


class TestMarkAmbiguousSlots:
    def test_disagreeing_stubs_marked_ambiguous(self):
        stubs = generate_candidate_stubs([_FUNC_AC])
        slots = mark_ambiguous_slots(stubs)
        assert slots  # generate variants disagree on return type
        assert all(isinstance(s, DisagreementSlot) for s in slots)
        assert all(s.uncertainty_score > UNCERTAINTY_THRESHOLD for s in slots)

    def test_identical_stubs_not_ambiguous(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        assert mark_ambiguous_slots(stubs) == []

    def test_threshold_one_returns_empty(self):
        stubs = generate_candidate_stubs([_FUNC_AC])
        assert mark_ambiguous_slots(stubs, threshold=1.0) == []

    def test_result_is_sorted(self):
        acs = ["Function defined: mod.zeta", "Function defined: mod.alpha"]
        stubs = generate_candidate_stubs(acs)
        slots = mark_ambiguous_slots(stubs)
        names = [s.slot_name for s in slots]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# build_clarification_questions
# ---------------------------------------------------------------------------


class TestBuildClarificationQuestions:
    def _slots(self):
        return [
            DisagreementSlot(
                slot_name="foo",
                provenance="F-R7-451",
                uncertainty_score=1.0,
                candidates=["bool", "int", "str", "None"],
                dimension="return_type",
            )
        ]

    def test_returns_one_question_per_slot(self):
        qs = build_clarification_questions(self._slots())
        assert len(qs) == 1
        assert isinstance(qs[0], ClarificationQuestion)

    def test_question_cites_provenance(self):
        qs = build_clarification_questions(self._slots())
        assert "F-R7-451" in qs[0].question_text
        assert qs[0].provenance == "F-R7-451"

    def test_choices_are_multiple_choice_with_other(self):
        qs = build_clarification_questions(self._slots())
        # 2-4 candidates + "Other"
        assert qs[0].choices[-1] == "Other"
        assert 3 <= len(qs[0].choices) <= 5

    def test_empty_slots_returns_empty(self):
        assert build_clarification_questions([]) == []

    def test_ci_mode_raises_spec_needs_human(self):
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            build_clarification_questions(self._slots(), ci_mode=True)

    def test_ci_mode_empty_slots_no_raise(self):
        assert build_clarification_questions([], ci_mode=True) == []


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_generate_non_list_raises(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_stubs("nope")  # type: ignore[arg-type]

    def test_generate_non_string_item_raises(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([123])  # type: ignore[list-item]

    def test_generate_n_candidates_zero_raises(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs([_FUNC_AC], n_candidates=0)

    def test_mark_non_list_raises(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            mark_ambiguous_slots("nope")  # type: ignore[arg-type]

    def test_mark_bad_threshold_raises(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            mark_ambiguous_slots([], threshold=1.5)

    def test_build_non_list_raises(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            build_clarification_questions("nope")  # type: ignore[arg-type]

    def test_build_bad_max_per_round_raises(self):
        with pytest.raises(ValueError, match="max_per_round"):
            build_clarification_questions([], max_per_round=6)


# ---------------------------------------------------------------------------
# Boundary paths
# ---------------------------------------------------------------------------


class TestBoundary:
    def test_generate_empty_list(self):
        assert generate_candidate_stubs([]) == []

    def test_mark_empty_stubs(self):
        assert mark_ambiguous_slots([]) == []

    def test_build_empty_slots(self):
        assert build_clarification_questions([]) == []

    def test_generate_n_candidates_one(self):
        stubs = generate_candidate_stubs([_FUNC_AC], n_candidates=1)
        assert len(stubs) == 1
