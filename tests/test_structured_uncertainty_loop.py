"""Tests for bob3.structured_uncertainty_loop.

Feature: 9ac6cdd1-459c-4a1b-943f-e1ef032d3526
Structured-uncertainty clarification loop with AskUserQuestion.
"""

from __future__ import annotations

import pytest

from bob3.structured_uncertainty_loop import (
    CandidateStub,
    ClarificationAnswer,
    SpecNeedsHumanError,
    UncertaintySlot,
    batch_clarification_questions,
    compute_uncertainty_slots,
    generate_candidate_stubs,
    UNCERTAINTY_THRESHOLD,
    SPEC_NEEDS_HUMAN,
    N_STUBS,
)


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    def test_returns_list_of_candidate_stubs(self):
        acs = ["Function defined: bob3.structured_uncertainty_loop.generate_candidate_stubs"]
        result = generate_candidate_stubs(acs)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_default_n_stubs_is_three(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs)
        assert len(result) == 3

    def test_n_stubs_parameter_respected(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs, n_stubs=2)
        assert len(result) == 2

    def test_multiple_function_acs(self):
        acs = [
            "Function defined: mymodule.func_a",
            "Function defined: mymodule.func_b",
        ]
        result = generate_candidate_stubs(acs)
        assert len(result) == 6  # 2 slots × 3 stubs

    def test_non_function_acs_ignored(self):
        acs = [
            "File exists: src/mymodule/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: mymodule.foo",
        ]
        result = generate_candidate_stubs(acs)
        assert len(result) == 3  # only the Function-defined AC counts

    def test_empty_ac_list_returns_empty(self):
        result = generate_candidate_stubs([])
        assert result == []

    def test_stub_has_required_fields(self):
        acs = ["Function defined: mymodule.check_something"]
        stubs = generate_candidate_stubs(acs, n_stubs=1)
        stub = stubs[0]
        assert stub.slot_name == "check_something"
        assert isinstance(stub.return_type, str)
        assert isinstance(stub.raised_exceptions, list)
        assert isinstance(stub.side_effects, list)
        assert isinstance(stub.raw_stub, str)

    def test_stubs_differ_in_observable_behaviour(self):
        """N=3 stubs for one slot must not all be identical."""
        acs = ["Function defined: mymodule.compute_score"]
        stubs = generate_candidate_stubs(acs, n_stubs=3)
        return_types = [s.return_type for s in stubs]
        # At least 2 variants must differ (the table covers 3 distinct values)
        assert len(set(return_types)) >= 2

    def test_class_defined_ac_also_extracted(self):
        acs = ["Class defined: mymodule.MyClass"]
        result = generate_candidate_stubs(acs, n_stubs=2)
        assert len(result) == 2
        assert all(s.slot_name == "MyClass" for s in result)

    def test_raises_value_error_for_non_list(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_stubs("not a list")  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_item(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([42])  # type: ignore[arg-type]

    def test_raises_value_error_for_n_stubs_zero(self):
        with pytest.raises(ValueError, match="n_stubs must be >= 1"):
            generate_candidate_stubs(["Function defined: foo.bar"], n_stubs=0)


# ---------------------------------------------------------------------------
# compute_uncertainty_slots
# ---------------------------------------------------------------------------


class TestComputeUncertaintySlots:
    def test_returns_list(self):
        acs = ["Function defined: mymodule.compute_score"]
        stubs = generate_candidate_stubs(acs, n_stubs=3)
        result = compute_uncertainty_slots(stubs)
        assert isinstance(result, list)

    def test_three_stubs_with_differing_return_types_yields_uncertain_slot(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = compute_uncertainty_slots(stubs, threshold=0.4)
        assert any(s.slot_name == "foo" and s.dimension == "return_type" for s in result)

    def test_identical_stubs_produce_no_uncertain_slots(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        result = compute_uncertainty_slots(stubs)
        assert result == []

    def test_empty_stubs_returns_empty(self):
        result = compute_uncertainty_slots([])
        assert result == []

    def test_uncertain_slot_has_required_fields(self):
        stubs = [
            CandidateStub("my_func", "bool", [], [], "..."),
            CandidateStub("my_func", "int", [], [], "..."),
            CandidateStub("my_func", "str", [], [], "..."),
        ]
        slots = compute_uncertainty_slots(stubs, threshold=0.0)
        assert len(slots) > 0
        slot = slots[0]
        assert isinstance(slot.slot_name, str)
        assert isinstance(slot.provenance, str)
        assert isinstance(slot.uncertainty_score, float)
        assert 0.0 <= slot.uncertainty_score <= 1.0
        assert isinstance(slot.candidates, list)
        assert isinstance(slot.dimension, str)

    def test_result_is_sorted_deterministically(self):
        stubs = [
            CandidateStub("z_func", "bool", [], [], "..."),
            CandidateStub("z_func", "int", [], [], "..."),
            CandidateStub("a_func", "None", [], [], "..."),
            CandidateStub("a_func", "str", [], [], "..."),
        ]
        result1 = compute_uncertainty_slots(stubs, threshold=0.0)
        result2 = compute_uncertainty_slots(stubs, threshold=0.0)
        assert [(s.slot_name, s.dimension) for s in result1] == [
            (s.slot_name, s.dimension) for s in result2
        ]

    def test_threshold_respected(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "..."),
            CandidateStub("foo", "int", [], [], "..."),
        ]
        # threshold=1.0 — nothing can exceed it
        result = compute_uncertainty_slots(stubs, threshold=1.0)
        assert result == []

    def test_raises_value_error_for_non_list_stubs(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            compute_uncertainty_slots("not a list")  # type: ignore[arg-type]

    def test_raises_value_error_for_threshold_out_of_range(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_uncertainty_slots([], threshold=1.5)

    def test_uses_default_uncertainty_threshold(self):
        assert UNCERTAINTY_THRESHOLD == 0.4


# ---------------------------------------------------------------------------
# batch_clarification_questions
# ---------------------------------------------------------------------------


class TestBatchClarificationQuestions:
    def test_empty_slots_returns_empty_list(self):
        result = batch_clarification_questions([])
        assert result == []

    def test_empty_slots_in_ci_mode_returns_empty_list(self):
        result = batch_clarification_questions([], ci_mode=True)
        assert result == []

    def test_ci_mode_with_ambiguous_slots_raises(self):
        slots = [
            UncertaintySlot("foo", "F-R7-451", 1.0, ["bool", "int"], "return_type"),
        ]
        with pytest.raises(SpecNeedsHumanError):
            batch_clarification_questions(slots, ci_mode=True)

    def test_ci_mode_error_contains_spec_needs_human_sentinel(self):
        slots = [
            UncertaintySlot("foo", "F-R7-451", 0.9, ["bool", "None"], "return_type"),
        ]
        with pytest.raises(SpecNeedsHumanError, match=SPEC_NEEDS_HUMAN):
            batch_clarification_questions(slots, ci_mode=True)

    def test_ci_mode_does_not_silently_succeed(self):
        """Ensures CI mode never returns answers when slots are ambiguous."""
        slots = [
            UncertaintySlot("bar", "F-R7-452", 0.8, ["A", "B"], "return_type"),
        ]
        raised = False
        try:
            batch_clarification_questions(slots, ci_mode=True)
        except SpecNeedsHumanError:
            raised = True
        assert raised

    def test_non_ci_mode_returns_answers(self, tmp_path):
        """Non-CI, non-TTY mode should auto-select and return answers."""
        slots = [
            UncertaintySlot("my_func", "F-R7-451", 0.6, ["bool", "int"], "return_type"),
        ]
        result = batch_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert isinstance(result[0], ClarificationAnswer)

    def test_answer_has_required_fields(self, tmp_path):
        slots = [
            UncertaintySlot("my_func", "F-R7-451", 0.6, ["bool", "int"], "return_type"),
        ]
        result = batch_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        answer = result[0]
        assert answer.slot_name == "my_func"
        assert answer.dimension == "return_type"
        assert isinstance(answer.selected, str)
        assert isinstance(answer.timestamp, str)

    def test_batching_processes_all_slots(self, tmp_path):
        """max_per_round=1 with 3 slots → all 3 processed, 3 answers."""
        slots = [
            UncertaintySlot("a", "F-R7-451", 1.0, ["bool", "int"], "return_type"),
            UncertaintySlot("b", "F-R7-452", 1.0, ["None", "str"], "return_type"),
            UncertaintySlot("c", "F-R7-453", 1.0, ["Any", "bool"], "return_type"),
        ]
        result = batch_clarification_questions(
            slots,
            max_per_round=1,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 3

    def test_audit_log_written(self, tmp_path):
        """Answers are appended to the audit log."""
        log_path = tmp_path / "clarifications.log"
        slots = [
            UncertaintySlot("my_func", "F-R7-451", 0.6, ["bool", "int"], "return_type"),
        ]
        batch_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=log_path,
        )
        assert log_path.exists()
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_raises_value_error_for_non_list_slots(self):
        with pytest.raises(ValueError, match="uncertain_slots must be a list"):
            batch_clarification_questions("not a list")  # type: ignore[arg-type]

    def test_raises_value_error_for_max_per_round_zero(self):
        with pytest.raises(ValueError, match="max_per_round"):
            batch_clarification_questions([], max_per_round=0)

    def test_raises_value_error_for_max_per_round_six(self):
        with pytest.raises(ValueError, match="max_per_round"):
            batch_clarification_questions([], max_per_round=6)


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_ci_mode_pipeline_raises_on_ambiguous_spec(self):
        """Full pipeline: generate stubs → compute uncertainty → CI raises."""
        acs = [
            "Function defined: mymodule.compute_score",
            "Function defined: mymodule.generate_report",
        ]
        stubs = generate_candidate_stubs(acs, n_stubs=3)
        uncertain = compute_uncertainty_slots(stubs, threshold=0.4)
        if uncertain:
            with pytest.raises(SpecNeedsHumanError):
                batch_clarification_questions(uncertain, ci_mode=True)

    def test_non_ci_pipeline_resolves_all_slots(self, tmp_path):
        """Full pipeline in non-CI mode produces one answer per uncertain slot."""
        acs = [
            "Function defined: mymodule.compute_score",
            "Function defined: mymodule.generate_report",
        ]
        stubs = generate_candidate_stubs(acs, n_stubs=3)
        uncertain = compute_uncertainty_slots(stubs, threshold=0.4)
        answers = batch_clarification_questions(
            uncertain,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(answers) == len(uncertain)

    def test_no_function_acs_produces_no_uncertainty(self):
        acs = [
            "File exists: src/mymodule/foo.py",
            "pytest: tests/test_foo.py",
        ]
        stubs = generate_candidate_stubs(acs)
        assert stubs == []
        uncertain = compute_uncertainty_slots(stubs)
        assert uncertain == []
