"""Boundary-case tests for spec_synthesis.uncertainty_loop.

Feature: 727ecb70-297d-4ca0-a774-f585e13821c6
AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import pytest

from spec_synthesis.uncertainty_loop import (
    compute_disagreement_slots,
    generate_candidate_stubs,
    trigger_clarification_questions,
)
from spec_synthesis import CandidateStub, DisagreementSlot


# ---------------------------------------------------------------------------
# generate_candidate_stubs — boundary cases
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubsBoundary:
    def test_empty_list_returns_empty(self):
        """Empty AC list → empty stub list, no exception."""
        result = generate_candidate_stubs([])
        assert result == []

    def test_single_non_function_ac_returns_empty(self):
        """Single 'File exists' AC → no stubs, no exception."""
        result = generate_candidate_stubs(["File exists: src/spec_synthesis/uncertainty_loop.py"])
        assert result == []

    def test_n_candidates_one_returns_single_stub(self):
        """n_candidates=1 → exactly one stub per slot, no exception."""
        acs = ["Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs"]
        result = generate_candidate_stubs(acs, n_candidates=1)
        assert len(result) == 1
        assert isinstance(result[0], CandidateStub)

    def test_ac_list_with_only_whitespace_strings(self):
        """ACs of only whitespace → no slots extracted, returns empty list."""
        result = generate_candidate_stubs(["   ", "\t", ""])
        assert result == []

    def test_single_function_ac_returns_n_stubs(self):
        """Minimum valid input (single Function-defined AC) succeeds."""
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs)
        assert len(result) == 3  # default N_CANDIDATES=3
        assert all(s.slot_name == "my_func" for s in result)


# ---------------------------------------------------------------------------
# compute_disagreement_slots — boundary cases
# ---------------------------------------------------------------------------


class TestComputeDisagreementSlotsBoundary:
    def test_empty_stubs_returns_empty(self):
        """Empty stubs list → empty disagreement list, no exception."""
        result = compute_disagreement_slots([])
        assert result == []

    def test_single_stub_returns_no_disagreement(self):
        """Single stub per slot → zero disagreement (nothing to compare)."""
        stubs = [
            CandidateStub(
                slot_name="foo",
                return_type="bool",
                raised_exceptions=[],
                side_effects=[],
                raw_stub="def foo(): return True",
            )
        ]
        result = compute_disagreement_slots(stubs)
        assert result == []

    def test_threshold_zero_includes_any_disagreement(self):
        """threshold=0.0 → any nonzero disagreement is above threshold."""
        # Two stubs with different return types → disagreement rate = 0.5 > 0
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = compute_disagreement_slots(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    def test_threshold_one_returns_empty(self):
        """threshold=1.0 → nothing can exceed threshold, returns empty."""
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = compute_disagreement_slots(stubs, threshold=1.0)
        assert result == []

    def test_two_identical_stubs_produce_no_disagreement(self):
        """Two identical stubs → disagreement=0.0 → empty list at default threshold."""
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        result = compute_disagreement_slots(stubs)
        assert result == []


# ---------------------------------------------------------------------------
# trigger_clarification_questions — boundary cases
# ---------------------------------------------------------------------------


class TestTriggerClarificationQuestionsBoundary:
    def test_empty_slots_returns_empty_list(self):
        """Zero slots → returns empty list without raising."""
        result = trigger_clarification_questions([])
        assert result == []

    def test_empty_slots_ci_mode_returns_empty(self):
        """Zero slots in CI mode → still returns empty list (nothing to block on)."""
        result = trigger_clarification_questions([], ci_mode=True)
        assert result == []

    def test_max_per_round_one_processes_all(self, tmp_path):
        """max_per_round=1 with 3 slots → processes each individually, no exception."""
        slots = [
            DisagreementSlot("a", "F-R7-451", 1.0, ["bool", "int"], "return_type"),
            DisagreementSlot("b", "F-R7-452", 1.0, ["None", "str"], "return_type"),
            DisagreementSlot("c", "F-R7-453", 1.0, ["Any", "bool"], "return_type"),
        ]
        result = trigger_clarification_questions(
            slots,
            max_per_round=1,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 3

    def test_single_slot_non_ci_returns_one_answer(self, tmp_path):
        """Minimum viable input: one slot in non-CI mode → one answer."""
        slots = [
            DisagreementSlot("foo", "F-R7-451", 0.5, ["bool", "int"], "return_type"),
        ]
        result = trigger_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert result[0].slot_name == "foo"
