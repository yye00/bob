"""Tests for spec_synthesis.uncertainty_loop.

Feature: 727ecb70-297d-4ca0-a774-f585e13821c6
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import os

import pytest

from spec_synthesis.uncertainty_loop import (
    compute_disagreement_slots,
    generate_candidate_stubs,
    trigger_clarification_questions,
)
from spec_synthesis import (
    CandidateStub,
    DisagreementSlot,
    SpecNeedsHumanError,
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    N_CANDIDATES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FUNC_ACS = [
    "Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs",
    "Function defined: spec_synthesis.uncertainty_loop.compute_disagreement_slots",
    "Function defined: spec_synthesis.uncertainty_loop.trigger_clarification_questions",
]


def _make_uniform_stubs(slot_name: str, n: int = 3) -> list[CandidateStub]:
    """Produce n stubs with identical observable behaviour (no disagreement)."""
    return [
        CandidateStub(
            slot_name=slot_name,
            return_type="bool",
            raised_exceptions=[],
            side_effects=[],
            raw_stub=f"def {slot_name}(): return True",
        )
        for _ in range(n)
    ]


def _make_disagreeing_stubs(slot_name: str) -> list[CandidateStub]:
    """Produce 3 stubs with fully distinct return types (max disagreement)."""
    return [
        CandidateStub(
            slot_name=slot_name,
            return_type=rt,
            raised_exceptions=[],
            side_effects=[],
            raw_stub=f"def {slot_name}(): ...",
        )
        for rt in ("bool", "dict[str, Any]", "list[str]")
    ]


def _make_disagreement_slot(slot_name: str = "foo") -> DisagreementSlot:
    return DisagreementSlot(
        slot_name=slot_name,
        provenance="F-R7-451",
        uncertainty_score=1.0,
        candidates=["bool", "dict[str, Any]", "list[str]"],
        dimension="return_type",
    )


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    def test_returns_list_of_candidate_stubs(self):
        result = generate_candidate_stubs(_FUNC_ACS)
        assert isinstance(result, list)
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_generates_n_stubs_per_slot(self):
        result = generate_candidate_stubs(_FUNC_ACS, n_candidates=3)
        slot_names = {s.slot_name for s in result}
        # 3 Function-defined ACs → 3 slots
        assert len(slot_names) == 3
        # Each slot has exactly 3 stubs
        for slot_name in slot_names:
            slot_stubs = [s for s in result if s.slot_name == slot_name]
            assert len(slot_stubs) == 3

    def test_file_exists_ac_produces_no_stubs(self):
        acs = ["File exists: src/spec_synthesis/uncertainty_loop.py"]
        result = generate_candidate_stubs(acs)
        assert result == []

    def test_n_candidates_parameter_respected(self):
        acs = ["Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs"]
        result = generate_candidate_stubs(acs, n_candidates=2)
        assert len(result) == 2

    def test_stubs_have_slot_name(self):
        acs = ["Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs"]
        result = generate_candidate_stubs(acs)
        for stub in result:
            assert stub.slot_name == "generate_candidate_stubs"

    def test_stubs_have_return_type(self):
        result = generate_candidate_stubs(_FUNC_ACS)
        for stub in result:
            assert isinstance(stub.return_type, str)
            assert stub.return_type  # non-empty

    def test_stubs_vary_in_observable_behaviour(self):
        acs = ["Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs"]
        result = generate_candidate_stubs(acs, n_candidates=3)
        return_types = [s.return_type for s in result]
        # At least 2 distinct return types (stubs disagree)
        assert len(set(return_types)) >= 2

    def test_empty_acs_returns_empty_list(self):
        result = generate_candidate_stubs([])
        assert result == []


# ---------------------------------------------------------------------------
# compute_disagreement_slots
# ---------------------------------------------------------------------------


class TestComputeDisagreementSlots:
    def test_returns_list_of_disagreement_slots(self):
        stubs = _make_disagreeing_stubs("foo")
        result = compute_disagreement_slots(stubs)
        assert isinstance(result, list)
        assert all(isinstance(s, DisagreementSlot) for s in result)

    def test_uniform_stubs_produce_no_disagreement(self):
        stubs = _make_uniform_stubs("foo")
        result = compute_disagreement_slots(stubs)
        assert result == []

    def test_disagreeing_return_types_produce_slot(self):
        stubs = _make_disagreeing_stubs("foo")
        result = compute_disagreement_slots(stubs)
        rt_slots = [s for s in result if s.dimension == "return_type"]
        assert len(rt_slots) == 1
        assert rt_slots[0].slot_name == "foo"
        assert rt_slots[0].uncertainty_score > UNCERTAINTY_THRESHOLD

    def test_uncertainty_score_above_threshold(self):
        stubs = _make_disagreeing_stubs("bar")
        result = compute_disagreement_slots(stubs)
        for slot in result:
            assert slot.uncertainty_score > UNCERTAINTY_THRESHOLD

    def test_threshold_filtering(self):
        stubs = _make_disagreeing_stubs("baz")
        # With very high threshold nothing should pass
        result = compute_disagreement_slots(stubs, threshold=1.0)
        assert result == []

    def test_slots_sorted_by_name_and_dimension(self):
        stubs = _make_disagreeing_stubs("a") + _make_disagreeing_stubs("b")
        result = compute_disagreement_slots(stubs)
        keys = [(s.slot_name, s.dimension) for s in result]
        assert keys == sorted(keys)

    def test_candidates_are_distinct_values(self):
        stubs = _make_disagreeing_stubs("foo")
        result = compute_disagreement_slots(stubs)
        for slot in result:
            assert len(slot.candidates) == len(set(slot.candidates))

    def test_empty_stubs_returns_empty(self):
        result = compute_disagreement_slots([])
        assert result == []

    def test_real_generated_stubs_produce_disagreement(self):
        acs = ["Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs"]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        # Real stubs vary → at least one disagreement slot
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# trigger_clarification_questions
# ---------------------------------------------------------------------------


class TestTriggerClarificationQuestions:
    def test_empty_slots_returns_empty_list(self):
        result = trigger_clarification_questions([])
        assert result == []

    def test_ci_mode_raises_spec_needs_human_error(self):
        slots = [_make_disagreement_slot()]
        with pytest.raises(SpecNeedsHumanError):
            trigger_clarification_questions(slots, ci_mode=True)

    def test_ci_mode_env_var_raises(self, monkeypatch):
        monkeypatch.setenv("BOB3_CI_MODE", "1")
        slots = [_make_disagreement_slot()]
        with pytest.raises(SpecNeedsHumanError):
            trigger_clarification_questions(slots)

    def test_non_ci_non_tty_returns_answers(self, tmp_path):
        slots = [_make_disagreement_slot()]
        result = trigger_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert isinstance(result, list)
        assert len(result) == 1

    def test_non_ci_non_tty_auto_selects(self, tmp_path):
        slots = [_make_disagreement_slot("x")]
        result = trigger_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        # Non-TTY auto-selects first candidate prefixed with "auto:"
        assert result[0].selected.startswith("auto:")

    def test_multiple_slots_all_answered(self, tmp_path):
        slots = [
            _make_disagreement_slot("alpha"),
            _make_disagreement_slot("beta"),
        ]
        result = trigger_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 2

    def test_answers_have_correct_slot_names(self, tmp_path):
        slots = [_make_disagreement_slot("my_func")]
        result = trigger_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert result[0].slot_name == "my_func"

    def test_audit_log_written(self, tmp_path):
        log = tmp_path / "clarifications.log"
        slots = [_make_disagreement_slot()]
        trigger_clarification_questions(
            slots,
            ci_mode=False,
            audit_log_path=log,
        )
        assert log.exists()
        assert log.read_text().strip() != ""

    def test_invalid_max_per_round_raises(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_clarification_questions([], max_per_round=6)

    def test_zero_max_per_round_raises(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_clarification_questions([], max_per_round=0)


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_generate_compute_trigger_pipeline_ci(self):
        """Full pipeline in CI mode returns SPEC_NEEDS_HUMAN when slots disagree."""
        acs = [
            "Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs",
        ]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        disagreements = compute_disagreement_slots(stubs)
        assert len(disagreements) >= 1

        with pytest.raises(SpecNeedsHumanError):
            trigger_clarification_questions(disagreements, ci_mode=True)

    def test_generate_compute_trigger_pipeline_non_ci(self, tmp_path):
        """Full pipeline in non-CI mode produces answers."""
        acs = [
            "Function defined: spec_synthesis.uncertainty_loop.generate_candidate_stubs",
        ]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        disagreements = compute_disagreement_slots(stubs)
        answers = trigger_clarification_questions(
            disagreements,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert isinstance(answers, list)
        assert len(answers) == len(disagreements)

    def test_no_function_acs_produces_no_disagreements(self):
        acs = [
            "File exists: src/spec_synthesis/uncertainty_loop.py",
            "pytest: tests/test_uncertainty_loop.py",
        ]
        stubs = generate_candidate_stubs(acs)
        assert stubs == []
        disagreements = compute_disagreement_slots(stubs)
        assert disagreements == []
        result = trigger_clarification_questions(disagreements)
        assert result == []
