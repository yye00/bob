"""Tests for spec_synthesis.uncertainty_clarification.

Feature: 06fb09db-6567-475f-888c-775a62883ed0
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import os

import pytest

from spec_synthesis.uncertainty_clarification import (
    compute_disagreement_threshold,
    generate_candidate_stubs,
    trigger_user_clarification,
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
    "Function defined: spec_synthesis.uncertainty_clarification.generate_candidate_stubs",
    "Function defined: spec_synthesis.uncertainty_clarification.compute_disagreement_threshold",
    "Function defined: spec_synthesis.uncertainty_clarification.trigger_user_clarification",
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


def _make_diverse_stubs(slot_name: str) -> list[CandidateStub]:
    """Produce 3 stubs with different return types (guaranteed disagreement)."""
    types = ["bool", "int", "str"]
    return [
        CandidateStub(
            slot_name=slot_name,
            return_type=rt,
            raised_exceptions=[],
            side_effects=[],
            raw_stub=f"def {slot_name}(): ...",
        )
        for rt in types
    ]


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    def test_returns_list(self):
        result = generate_candidate_stubs(_FUNC_ACS)
        assert isinstance(result, list)

    def test_returns_candidate_stubs(self):
        result = generate_candidate_stubs(_FUNC_ACS)
        assert all(isinstance(s, CandidateStub) for s in result)

    def test_n_candidates_default(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs)
        assert len(result) == N_CANDIDATES

    def test_n_candidates_custom(self):
        acs = ["Function defined: mymodule.my_func"]
        result = generate_candidate_stubs(acs, n_candidates=2)
        assert len(result) == 2

    def test_empty_acs_returns_empty(self):
        result = generate_candidate_stubs([])
        assert result == []

    def test_non_function_acs_return_empty(self):
        acs = ["File exists: src/spec_synthesis/uncertainty_clarification.py"]
        result = generate_candidate_stubs(acs)
        assert result == []

    def test_stub_slot_names(self):
        acs = ["Function defined: mymod.my_func"]
        result = generate_candidate_stubs(acs)
        assert all(s.slot_name == "my_func" for s in result)

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_stubs("not a list")  # type: ignore[arg-type]

    def test_non_string_item_raises(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([123])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(["Function defined: foo.bar"], n_candidates=0)

    def test_n_candidates_negative_raises(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(["Function defined: foo.bar"], n_candidates=-1)

    def test_none_raises(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs(None)  # type: ignore[arg-type]

    def test_list_with_none_element_raises(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs([None])  # type: ignore[arg-type]

    def test_multiple_function_acs(self):
        acs = [
            "Function defined: mod.func_a",
            "Function defined: mod.func_b",
        ]
        result = generate_candidate_stubs(acs)
        assert len(result) == 2 * N_CANDIDATES
        slot_names = {s.slot_name for s in result}
        assert slot_names == {"func_a", "func_b"}


# ---------------------------------------------------------------------------
# compute_disagreement_threshold
# ---------------------------------------------------------------------------


class TestComputeDisagreementThreshold:
    def test_returns_list(self):
        result = compute_disagreement_threshold([])
        assert isinstance(result, list)

    def test_empty_stubs_returns_empty(self):
        result = compute_disagreement_threshold([])
        assert result == []

    def test_uniform_stubs_no_disagreement(self):
        stubs = _make_uniform_stubs("foo")
        result = compute_disagreement_threshold(stubs)
        assert result == []

    def test_diverse_stubs_produce_disagreement(self):
        stubs = _make_diverse_stubs("foo")
        result = compute_disagreement_threshold(stubs)
        assert any(s.dimension == "return_type" for s in result)

    def test_threshold_above_default_may_suppress(self):
        stubs = _make_diverse_stubs("foo")
        # disagreement rate for 3 distinct out of 3 = 1.0 > 0.9
        result_high = compute_disagreement_threshold(stubs, threshold=0.9)
        result_default = compute_disagreement_threshold(stubs, threshold=UNCERTAINTY_THRESHOLD)
        # With higher threshold, may have fewer or equal slots flagged
        assert len(result_high) <= len(result_default)

    def test_threshold_zero_catches_any_disagreement(self):
        stubs = [
            CandidateStub("foo", "bool", [], [], "def foo(): ..."),
            CandidateStub("foo", "int", [], [], "def foo(): ..."),
        ]
        result = compute_disagreement_threshold(stubs, threshold=0.0)
        assert any(s.dimension == "return_type" for s in result)

    def test_threshold_one_returns_empty(self):
        stubs = _make_diverse_stubs("foo")
        result = compute_disagreement_threshold(stubs, threshold=1.0)
        assert result == []

    def test_non_list_raises(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            compute_disagreement_threshold("not a list")  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises(ValueError):
            compute_disagreement_threshold(None)  # type: ignore[arg-type]

    def test_threshold_below_zero_raises(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_disagreement_threshold([], threshold=-0.1)

    def test_threshold_above_one_raises(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_disagreement_threshold([], threshold=1.1)

    def test_single_stub_no_disagreement(self):
        stubs = [CandidateStub("foo", "bool", [], [], "def foo(): ...")]
        result = compute_disagreement_threshold(stubs)
        assert result == []

    def test_disagreement_slots_have_required_fields(self):
        stubs = _make_diverse_stubs("foo")
        result = compute_disagreement_threshold(stubs)
        for slot in result:
            assert isinstance(slot, DisagreementSlot)
            assert slot.slot_name == "foo"
            assert slot.uncertainty_score > UNCERTAINTY_THRESHOLD
            assert slot.provenance.startswith("F-R7-")
            assert isinstance(slot.candidates, list)

    def test_result_sorted_by_slot_name_dimension(self):
        stubs_a = _make_diverse_stubs("aaa")
        stubs_b = _make_diverse_stubs("bbb")
        result = compute_disagreement_threshold(stubs_a + stubs_b)
        names = [s.slot_name for s in result]
        assert names == sorted(names)


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

    def test_ci_mode_with_ambiguous_slots_raises(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=1.0,
            candidates=["bool", "int", "str"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError):
            trigger_user_clarification([slot], ci_mode=True)

    def test_ci_mode_error_contains_spec_needs_human(self):
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "None"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            trigger_user_clarification([slot], ci_mode=True)

    def test_non_ci_single_slot_returns_one_answer(self, tmp_path):
        slot = DisagreementSlot(
            slot_name="foo",
            provenance="F-R7-451",
            uncertainty_score=0.5,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        result = trigger_user_clarification(
            [slot],
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1
        assert result[0].slot_name == "foo"

    def test_non_list_raises(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            trigger_user_clarification("not a list")  # type: ignore[arg-type]

    def test_none_slots_raises(self):
        with pytest.raises(ValueError):
            trigger_user_clarification(None)  # type: ignore[arg-type]

    def test_max_per_round_zero_raises(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=0)

    def test_max_per_round_six_raises(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=6)

    def test_max_per_round_negative_raises(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_user_clarification([], max_per_round=-1)

    def test_max_per_round_one_processes_all(self, tmp_path):
        slots = [
            DisagreementSlot("a", "F-R7-451", 1.0, ["bool", "int"], "return_type"),
            DisagreementSlot("b", "F-R7-452", 1.0, ["None", "str"], "return_type"),
            DisagreementSlot("c", "F-R7-453", 1.0, ["Any", "bool"], "return_type"),
        ]
        result = trigger_user_clarification(
            slots,
            max_per_round=1,
            ci_mode=False,
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 3

    def test_ci_mode_never_silently_returns(self):
        slot = DisagreementSlot(
            slot_name="risky_func",
            provenance="F-R7-999",
            uncertainty_score=0.8,
            candidates=["A", "B"],
            dimension="return_type",
        )
        raised = False
        try:
            trigger_user_clarification([slot], ci_mode=True)
        except SpecNeedsHumanError:
            raised = True
        assert raised, "Expected SpecNeedsHumanError but no exception was raised"

    def test_env_var_ci_mode_truthy(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOB_CI_MODE", "1")
        slot = DisagreementSlot(
            slot_name="foo",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError):
            trigger_user_clarification([slot], audit_log_path=tmp_path / "clarifications.log")

    def test_env_var_ci_mode_falsy(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOB_CI_MODE", "0")
        slot = DisagreementSlot(
            slot_name="foo",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "int"],
            dimension="return_type",
        )
        result = trigger_user_clarification(
            [slot],
            audit_log_path=tmp_path / "clarifications.log",
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_generate_then_threshold_then_clarify(self, tmp_path):
        acs = [
            "Function defined: spec_synthesis.uncertainty_clarification.generate_candidate_stubs",
            "Function defined: spec_synthesis.uncertainty_clarification.compute_disagreement_threshold",
        ]
        stubs = generate_candidate_stubs(acs)
        assert len(stubs) > 0

        slots = compute_disagreement_threshold(stubs)
        assert isinstance(slots, list)

        # In CI mode, should either raise or return empty list
        if slots:
            with pytest.raises(SpecNeedsHumanError):
                trigger_user_clarification(slots, ci_mode=True)
        else:
            result = trigger_user_clarification(slots, ci_mode=True)
            assert result == []

    def test_pipeline_with_no_function_acs(self, tmp_path):
        acs = ["File exists: src/spec_synthesis/uncertainty_clarification.py"]
        stubs = generate_candidate_stubs(acs)
        assert stubs == []

        slots = compute_disagreement_threshold(stubs)
        assert slots == []

        result = trigger_user_clarification(slots, ci_mode=True)
        assert result == []
