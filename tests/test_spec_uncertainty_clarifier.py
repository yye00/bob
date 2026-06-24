"""Tests for bob.spec_uncertainty_clarifier.

Feature: 5a7be040-b4c9-4beb-b3c0-0b6d0caecf60
Structured-uncertainty clarification loop with AskUserQuestion.
"""

from __future__ import annotations

import pytest

from bob.spec_uncertainty_clarifier import (
    batch_clarification_questions,
    detect_disagreement_slots,
    generate_candidate_stubs,
)
from spec_synthesis import (
    CandidateStub,
    ClarificationAnswer,
    DisagreementSlot,
    N_CANDIDATES,
    UNCERTAINTY_THRESHOLD,
    SpecNeedsHumanError,
)


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    def test_empty_list_returns_empty(self):
        result = generate_candidate_stubs([])
        assert result == []

    def test_non_function_acs_only_returns_empty(self):
        result = generate_candidate_stubs(["File exists: src/foo.py"])
        assert result == []

    def test_single_function_ac_returns_n_candidates(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs)
        assert len(result) == N_CANDIDATES
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_n_candidates_one_returns_one_stub(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs, n_candidates=1)
        assert len(result) == 1

    def test_multiple_function_acs_return_multiple_stubs(self):
        acs = [
            "Function defined: mymodule.func_a",
            "Function defined: mymodule.func_b",
        ]
        result = generate_candidate_stubs(acs)
        assert len(result) == N_CANDIDATES * 2

    def test_whitespace_only_acs_return_empty(self):
        result = generate_candidate_stubs(["   ", "\t", ""])
        assert result == []

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_stubs("not a list")  # type: ignore[arg-type]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs(None)  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([123])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(["Function defined: foo.bar"], n_candidates=0)

    def test_n_candidates_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(["Function defined: foo.bar"], n_candidates=-1)


# ---------------------------------------------------------------------------
# detect_disagreement_slots
# ---------------------------------------------------------------------------


class TestDetectDisagreementSlots:
    def test_empty_stubs_returns_empty(self):
        result = detect_disagreement_slots([])
        assert result == []

    def test_single_stub_no_disagreement(self):
        stubs = [CandidateStub("foo", "bool", [], [], "def foo(): return True")]
        result = detect_disagreement_slots(stubs)
        assert result == []

    def test_identical_stubs_no_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        result = detect_disagreement_slots(stubs)
        assert result == []

    def test_differing_return_types_detected_above_threshold(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = detect_disagreement_slots(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    def test_threshold_one_returns_empty(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = detect_disagreement_slots(stubs, threshold=1.0)
        assert result == []

    def test_returns_list_of_disagreement_slots(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = detect_disagreement_slots(stubs, threshold=0.0)
        assert all(isinstance(s, DisagreementSlot) for s in result)

    def test_non_list_stubs_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            detect_disagreement_slots("not a list")  # type: ignore[arg-type]

    def test_none_stubs_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_disagreement_slots(None)  # type: ignore[arg-type]

    def test_threshold_below_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            detect_disagreement_slots([], threshold=-0.1)

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            detect_disagreement_slots([], threshold=1.1)


# ---------------------------------------------------------------------------
# batch_clarification_questions
# ---------------------------------------------------------------------------


class TestBatchClarificationQuestions:
    def test_empty_slots_returns_empty(self):
        result = batch_clarification_questions([])
        assert result == []

    def test_empty_slots_ci_mode_returns_empty(self):
        result = batch_clarification_questions([], ci_mode=True)
        assert result == []

    def test_ci_mode_with_slots_raises_spec_needs_human(self):
        slot = DisagreementSlot("foo", "F-R7-451", 0.9, ["bool", "int"], "return_type")
        with pytest.raises(SpecNeedsHumanError):
            batch_clarification_questions([slot], ci_mode=True)

    def test_ci_mode_error_contains_spec_needs_human_sentinel(self):
        slot = DisagreementSlot("foo", "F-R7-451", 0.9, ["bool", "int"], "return_type")
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            batch_clarification_questions([slot], ci_mode=True)

    def test_ci_mode_never_returns_answer_for_ambiguous_slots(self):
        slot = DisagreementSlot("risky", "F-R7-999", 0.8, ["A", "B"], "return_type")
        raised = False
        try:
            batch_clarification_questions([slot], ci_mode=True)
        except SpecNeedsHumanError:
            raised = True
        assert raised

    def test_non_list_slots_raises_value_error(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            batch_clarification_questions("not a list")  # type: ignore[arg-type]

    def test_none_slots_raises_value_error(self):
        with pytest.raises(ValueError):
            batch_clarification_questions(None)  # type: ignore[arg-type]

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            batch_clarification_questions([], max_per_round=0)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            batch_clarification_questions([], max_per_round=6)

    def test_max_per_round_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            batch_clarification_questions([], max_per_round=-1)

    def test_non_ci_mode_single_slot_returns_answer(self, tmp_path):
        slot = DisagreementSlot("foo", "F-R7-451", 0.5, ["bool", "int"], "return_type")
        result = batch_clarification_questions(
            [slot],
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert isinstance(result[0], ClarificationAnswer)

    def test_non_ci_mode_multiple_slots_returns_all_answers(self, tmp_path):
        slots = [
            DisagreementSlot("a", "F-R7-451", 0.9, ["bool", "int"], "return_type"),
            DisagreementSlot("b", "F-R7-452", 0.8, ["None", "str"], "return_type"),
        ]
        result = batch_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_end_to_end_ci_mode_with_ambiguous_spec(self):
        """Full pipeline: stubs → detect ambiguity → CI raises SpecNeedsHumanError."""
        acs = [
            "Function defined: mymodule.do_something",
        ]
        stubs = generate_candidate_stubs(acs)
        assert len(stubs) == N_CANDIDATES

        slots = detect_disagreement_slots(stubs, threshold=0.0)

        if slots:
            with pytest.raises(SpecNeedsHumanError):
                batch_clarification_questions(slots, ci_mode=True)
        else:
            answers = batch_clarification_questions(slots, ci_mode=True)
            assert answers == []

    def test_end_to_end_no_ambiguity_returns_no_questions(self):
        """Identical stubs → no slots → batch returns empty without raising."""
        # Inject identical stubs directly (no ambiguity)
        stubs = [
            CandidateStub("foo", "None", [], [], "def foo(): pass"),
            CandidateStub("foo", "None", [], [], "def foo(): pass"),
            CandidateStub("foo", "None", [], [], "def foo(): pass"),
        ]
        slots = detect_disagreement_slots(stubs)
        assert slots == []

        answers = batch_clarification_questions(slots, ci_mode=True)
        assert answers == []
