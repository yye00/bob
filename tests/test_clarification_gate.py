"""Tests for bob.clarification_gate.

Feature: 0702426d-5276-4654-9ee2-1a373d6f1e99
Covers: generate_candidate_stubs, compute_disagreement_score, build_clarification_questions
"""

from __future__ import annotations

import pytest

from bob.clarification_gate import (
    build_clarification_questions,
    compute_disagreement_score,
    generate_candidate_stubs,
)
from spec_synthesis import CandidateStub, DisagreementSlot, SpecNeedsHumanError


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    def test_empty_acs_returns_empty(self):
        assert generate_candidate_stubs([]) == []

    def test_non_function_ac_returns_empty(self):
        result = generate_candidate_stubs(["File exists: src/bob/clarification_gate.py"])
        assert result == []

    def test_function_ac_returns_n_stubs(self):
        acs = ["Function defined: bob.clarification_gate.generate_candidate_stubs"]
        result = generate_candidate_stubs(acs)
        assert len(result) == 3
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_n_candidates_respected(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs, n_candidates=2)
        assert len(result) == 2

    def test_multiple_function_acs_produce_multiple_stub_sets(self):
        acs = [
            "Function defined: mymodule.func_a",
            "Function defined: mymodule.func_b",
        ]
        result = generate_candidate_stubs(acs)
        assert len(result) == 6  # 3 stubs × 2 functions

    def test_slot_names_extracted_correctly(self):
        acs = ["Function defined: mymodule.compute_score"]
        result = generate_candidate_stubs(acs)
        assert all(s.slot_name == "compute_score" for s in result)

    def test_stubs_have_required_fields(self):
        acs = ["Function defined: mymodule.run_loop"]
        result = generate_candidate_stubs(acs)
        for stub in result:
            assert hasattr(stub, "slot_name")
            assert hasattr(stub, "return_type")
            assert hasattr(stub, "raised_exceptions")
            assert hasattr(stub, "side_effects")
            assert hasattr(stub, "raw_stub")

    # Error paths
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
            generate_candidate_stubs(["Function defined: foo.bar"], n_candidates=-5)


# ---------------------------------------------------------------------------
# compute_disagreement_score
# ---------------------------------------------------------------------------


class TestComputeDisagreementScore:
    def test_empty_stubs_returns_empty(self):
        assert compute_disagreement_score([]) == []

    def test_single_stub_returns_no_disagreement(self):
        stubs = [CandidateStub("foo", "bool", [], [], "def foo(): return True")]
        assert compute_disagreement_score(stubs) == []

    def test_identical_stubs_produce_no_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
            CandidateStub("foo", "bool", [], [], "def foo(): return True"),
        ]
        assert compute_disagreement_score(stubs) == []

    def test_disagreeing_return_types_above_threshold(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = compute_disagreement_score(stubs)
        assert any(s.dimension == "return_type" for s in result)

    def test_returns_list_of_disagreement_slots(self):
        stubs = [
            CandidateStub("bar", "bool", [], [], "def bar(): ..."),
            CandidateStub("bar", "int", [], [], "def bar(): ..."),
            CandidateStub("bar", "None", [], [], "def bar(): ..."),
        ]
        result = compute_disagreement_score(stubs)
        assert all(isinstance(s, DisagreementSlot) for s in result)

    def test_threshold_one_returns_empty(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        assert compute_disagreement_score(stubs, threshold=1.0) == []

    def test_threshold_zero_includes_any_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = compute_disagreement_score(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    # Error paths
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            compute_disagreement_score("not a list")  # type: ignore[arg-type]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_disagreement_score(None)  # type: ignore[arg-type]

    def test_threshold_below_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_disagreement_score([], threshold=-0.1)

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_disagreement_score([], threshold=1.1)


# ---------------------------------------------------------------------------
# build_clarification_questions
# ---------------------------------------------------------------------------


class TestBuildClarificationQuestions:
    def test_empty_slots_returns_empty(self):
        result = build_clarification_questions([])
        assert result == []

    def test_empty_slots_ci_mode_returns_empty(self):
        result = build_clarification_questions([], ci_mode=True)
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
            build_clarification_questions([slot], ci_mode=True)

    def test_ci_mode_error_contains_spec_needs_human_sentinel(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "None"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            build_clarification_questions([slot], ci_mode=True)

    def test_non_ci_non_tty_returns_answers(self, tmp_path):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        result = build_clarification_questions(
            [slot],
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert result[0].slot_name == "my_func"

    def test_audit_log_written(self, tmp_path):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        log_path = tmp_path / "clarifications.log"
        build_clarification_questions(
            [slot],
            ci_mode=False,
            audit_log_path=log_path,
        )
        assert log_path.exists()
        content = log_path.read_text()
        assert "my_func" in content

    # Error paths
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            build_clarification_questions("not a list")  # type: ignore[arg-type]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            build_clarification_questions(None)  # type: ignore[arg-type]

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            build_clarification_questions([], max_per_round=0)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            build_clarification_questions([], max_per_round=6)

    def test_max_per_round_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            build_clarification_questions([], max_per_round=-1)


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestClarificationGatePipeline:
    def test_pipeline_ci_mode_spec_needs_human(self):
        """Full pipeline: stubs → disagreements → CI gate raises."""
        acs = [
            "Function defined: bob.clarification_gate.generate_candidate_stubs",
            "Function defined: bob.clarification_gate.compute_disagreement_score",
            "Function defined: bob.clarification_gate.build_clarification_questions",
        ]
        stubs = generate_candidate_stubs(acs)
        slots = compute_disagreement_score(stubs)
        if slots:
            with pytest.raises(SpecNeedsHumanError):
                build_clarification_questions(slots, ci_mode=True)

    def test_pipeline_no_function_acs_all_clear(self):
        """No function ACs → no stubs → no disagreements → empty questions."""
        acs = ["File exists: src/bob/clarification_gate.py"]
        stubs = generate_candidate_stubs(acs)
        slots = compute_disagreement_score(stubs)
        result = build_clarification_questions(slots, ci_mode=True)
        assert result == []
