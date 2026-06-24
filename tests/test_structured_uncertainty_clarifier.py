"""Tests for bob.structured_uncertainty_clarifier.

Feature: 5cca9b1c-d089-4071-a9e6-18331c399575
Structured-uncertainty clarification loop with AskUserQuestion.
"""

from __future__ import annotations

import pytest

from bob.structured_uncertainty_clarifier import (
    detect_disagreement_slots,
    generate_candidate_implementations,
    trigger_user_clarification,
)
from spec_synthesis import CandidateStub, DisagreementSlot, SpecNeedsHumanError


# ---------------------------------------------------------------------------
# generate_candidate_implementations
# ---------------------------------------------------------------------------


class TestGenerateCandidateImplementations:
    def test_returns_list_of_candidate_stubs(self):
        acs = ["Function defined: bob.structured_uncertainty_clarifier.generate_candidate_implementations"]
        result = generate_candidate_implementations(acs)
        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_empty_list_returns_empty(self):
        result = generate_candidate_implementations([])
        assert result == []

    def test_non_function_ac_returns_empty(self):
        result = generate_candidate_implementations(["File exists: src/bob/foo.py"])
        assert result == []

    def test_n_candidates_respected(self):
        acs = ["Function defined: mymod.my_func"]
        result = generate_candidate_implementations(acs, n_candidates=2)
        assert len(result) == 2

    def test_multiple_function_acs(self):
        acs = [
            "Function defined: mymod.func_a",
            "Function defined: mymod.func_b",
        ]
        result = generate_candidate_implementations(acs)
        assert len(result) == 6  # 2 slots × 3 candidates

    def test_slot_names_match_function_name(self):
        acs = ["Function defined: mymod.compute_score"]
        result = generate_candidate_implementations(acs)
        assert all(s.slot_name == "compute_score" for s in result)

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_implementations("not a list")  # type: ignore[arg-type]

    def test_non_string_item_raises_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_implementations([123])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_implementations(["Function defined: m.f"], n_candidates=0)


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
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
        ]
        result = detect_disagreement_slots(stubs)
        assert result == []

    def test_disagreeing_stubs_produce_slot(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
            CandidateStub("foo", "str", [], [], "def foo(): ..."),
        ]
        result = detect_disagreement_slots(stubs)
        assert any(s.dimension == "return_type" for s in result)

    def test_result_contains_disagreement_slot_instances(self):
        stubs = [
            CandidateStub("bar", "None", [], [], "def bar(): ..."),
            CandidateStub("bar", "dict", [], [], "def bar(): ..."),
            CandidateStub("bar", "list", [], [], "def bar(): ..."),
        ]
        result = detect_disagreement_slots(stubs)
        assert all(isinstance(s, DisagreementSlot) for s in result)

    def test_threshold_one_returns_empty(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], ""),
            CandidateStub("foo", "int", [], [], ""),
        ]
        result = detect_disagreement_slots(stubs, threshold=1.0)
        assert result == []

    def test_threshold_zero_catches_any_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], ""),
            CandidateStub("foo", "int", [], [], ""),
        ]
        result = detect_disagreement_slots(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            detect_disagreement_slots("not a list")  # type: ignore[arg-type]

    def test_threshold_out_of_range_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            detect_disagreement_slots([], threshold=1.5)

    def test_threshold_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            detect_disagreement_slots([], threshold=-0.1)


# ---------------------------------------------------------------------------
# trigger_user_clarification
# ---------------------------------------------------------------------------


class TestTriggerUserClarification:
    def test_empty_slots_returns_empty_list(self):
        result = trigger_user_clarification([])
        assert result == []

    def test_empty_slots_ci_mode_returns_empty(self):
        result = trigger_user_clarification([], ci_mode=True)
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
            trigger_user_clarification([slot], ci_mode=True)

    def test_ci_mode_error_contains_sentinel(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            trigger_user_clarification([slot], ci_mode=True)

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            trigger_user_clarification("not a list")  # type: ignore[arg-type]

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=0)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=6)

    def test_non_ci_non_tty_auto_selects(self, tmp_path):
        slot = DisagreementSlot(
            slot_name="compute",
            provenance="F-R7-451",
            uncertainty_score=0.7,
            candidates=["float", "int"],
            dimension="return_type",
        )
        result = trigger_user_clarification(
            [slot],
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert result[0].slot_name == "compute"


# ---------------------------------------------------------------------------
# Integration: generate → detect → trigger pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_pipeline_ci_mode_blocked(self):
        acs = [
            "Function defined: bob.structured_uncertainty_clarifier.generate_candidate_implementations",
            "Function defined: bob.structured_uncertainty_clarifier.detect_disagreement_slots",
            "Function defined: bob.structured_uncertainty_clarifier.trigger_user_clarification",
        ]
        stubs = generate_candidate_implementations(acs)
        assert len(stubs) > 0

        slots = detect_disagreement_slots(stubs)
        # Slots may or may not have disagreements depending on stub generation
        assert isinstance(slots, list)

        if slots:
            with pytest.raises(SpecNeedsHumanError):
                trigger_user_clarification(slots, ci_mode=True)
        else:
            result = trigger_user_clarification(slots, ci_mode=True)
            assert result == []
