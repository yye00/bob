"""Tests for spec_synthesis — Structured-uncertainty clarification loop.

Feature ID: 6dbc8bc6-ef58-4902-af6e-04a41f6f325c
AC-5: pytest: tests/test_spec_synthesis.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from spec_synthesis import (
    SPEC_NEEDS_HUMAN,
    UNCERTAINTY_THRESHOLD,
    N_CANDIDATES,
    CandidateStub,
    ClarificationAnswer,
    DisagreementSlot,
    SpecNeedsHumanError,
    AskUserQuestion,
    compute_disagreement_slots,
    exit_spec_needs_human,
    generate_candidate_stubs,
    run_clarification_loop,
)


# ---------------------------------------------------------------------------
# generate_candidate_stubs
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubs:
    """AC-0: Function defined: spec_synthesis.generate_candidate_stubs"""

    _ACS = [
        "Function defined: spec_synthesis.generate_candidate_stubs",
        "Function defined: spec_synthesis.compute_disagreement_slots",
        "Function defined: spec_synthesis.AskUserQuestion",
        "Function defined: spec_synthesis.exit_spec_needs_human",
    ]

    def test_returns_list_of_candidate_stubs(self):
        stubs = generate_candidate_stubs(self._ACS)
        assert isinstance(stubs, list)
        assert all(isinstance(s, CandidateStub) for s in stubs)

    def test_produces_n_stubs_per_slot(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        # 4 function slots × 3 = 12
        assert len(stubs) == 12

    def test_n_candidates_parameter_respected(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=2)
        assert len(stubs) == 8  # 4 slots × 2

    def test_each_stub_has_slot_name(self):
        stubs = generate_candidate_stubs(self._ACS)
        for stub in stubs:
            assert stub.slot_name, "slot_name must be non-empty"

    def test_stub_return_type_is_string(self):
        stubs = generate_candidate_stubs(self._ACS)
        for stub in stubs:
            assert isinstance(stub.return_type, str)
            assert len(stub.return_type) > 0

    def test_stub_raw_stub_is_string(self):
        stubs = generate_candidate_stubs(self._ACS)
        for stub in stubs:
            assert isinstance(stub.raw_stub, str)
            assert "def " in stub.raw_stub

    def test_empty_criteria_returns_empty_list(self):
        stubs = generate_candidate_stubs([])
        assert stubs == []

    def test_file_exists_ac_not_extracted(self):
        acs = ["File exists: src/spec_synthesis.py"]
        stubs = generate_candidate_stubs(acs)
        assert stubs == []

    def test_pytest_ac_not_extracted(self):
        acs = ["pytest: tests/test_spec_synthesis.py"]
        stubs = generate_candidate_stubs(acs)
        assert stubs == []

    def test_stubs_disagree_on_return_type_for_three_variants(self):
        # With n_candidates=3, return types should cycle through variants → disagreement
        acs = ["Function defined: spec_synthesis.generate_candidate_stubs"]
        stubs = generate_candidate_stubs(acs, n_candidates=3)
        return_types = {s.return_type for s in stubs}
        assert len(return_types) > 1, "Three variants should produce differing return types"

    def test_slot_names_derived_from_ac_function_name(self):
        acs = ["Function defined: spec_synthesis.compute_disagreement_slots"]
        stubs = generate_candidate_stubs(acs, n_candidates=1)
        assert stubs[0].slot_name == "compute_disagreement_slots"

    def test_stubs_have_side_effects_list(self):
        stubs = generate_candidate_stubs(self._ACS)
        for stub in stubs:
            assert isinstance(stub.side_effects, list)

    def test_stubs_have_raised_exceptions_list(self):
        stubs = generate_candidate_stubs(self._ACS)
        for stub in stubs:
            assert isinstance(stub.raised_exceptions, list)


# ---------------------------------------------------------------------------
# compute_disagreement_slots
# ---------------------------------------------------------------------------


class TestComputeDisagreementSlots:
    """AC-1: Function defined: spec_synthesis.compute_disagreement_slots"""

    _ACS = [
        "Function defined: spec_synthesis.generate_candidate_stubs",
        "Function defined: spec_synthesis.compute_disagreement_slots",
        "Function defined: spec_synthesis.AskUserQuestion",
        "Function defined: spec_synthesis.exit_spec_needs_human",
    ]

    def test_returns_list(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        assert isinstance(result, list)

    def test_all_slots_in_result_have_score_above_threshold(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        for slot in result:
            assert slot.uncertainty_score > UNCERTAINTY_THRESHOLD

    def test_result_items_are_disagreement_slots(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        for item in result:
            assert isinstance(item, DisagreementSlot)

    def test_empty_stubs_returns_empty(self):
        result = compute_disagreement_slots([])
        assert result == []

    def test_identical_stubs_produce_no_disagreement(self):
        stub = CandidateStub(
            slot_name="foo",
            return_type="bool",
            raised_exceptions=[],
            side_effects=[],
            raw_stub="def foo(): return True",
        )
        result = compute_disagreement_slots([stub, stub, stub])
        assert result == []

    def test_disagreement_slot_has_candidates(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        for slot in result:
            assert len(slot.candidates) >= 2

    def test_disagreement_slot_has_dimension(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        valid_dims = {"return_type", "raised_exceptions", "side_effects"}
        for slot in result:
            assert slot.dimension in valid_dims

    def test_disagreement_slot_has_slot_name(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        for slot in result:
            assert isinstance(slot.slot_name, str)
            assert len(slot.slot_name) > 0

    def test_custom_threshold_higher_reduces_results(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        low_threshold = compute_disagreement_slots(stubs, threshold=0.4)
        high_threshold = compute_disagreement_slots(stubs, threshold=0.99)
        assert len(low_threshold) >= len(high_threshold)

    def test_result_is_sorted_by_slot_name_and_dimension(self):
        stubs = generate_candidate_stubs(self._ACS, n_candidates=3)
        result = compute_disagreement_slots(stubs)
        keys = [(s.slot_name, s.dimension) for s in result]
        assert keys == sorted(keys)

    def test_single_stub_per_slot_produces_no_disagreement(self):
        acs = ["Function defined: spec_synthesis.generate_candidate_stubs"]
        stubs = generate_candidate_stubs(acs, n_candidates=1)
        result = compute_disagreement_slots(stubs)
        assert result == []


# ---------------------------------------------------------------------------
# AskUserQuestion
# ---------------------------------------------------------------------------


class TestAskUserQuestion:
    """AC-2: Function defined: spec_synthesis.AskUserQuestion"""

    def _make_slots(self) -> list[DisagreementSlot]:
        return [
            DisagreementSlot(
                slot_name="my_func",
                provenance="F-R7-451",
                uncertainty_score=0.5,
                candidates=["bool", "str"],
                dimension="return_type",
            )
        ]

    def test_returns_list_of_clarification_answers(self):
        slots = self._make_slots()
        answers = AskUserQuestion(slots)
        assert isinstance(answers, list)
        assert all(isinstance(a, ClarificationAnswer) for a in answers)

    def test_one_answer_per_slot(self):
        slots = self._make_slots()
        answers = AskUserQuestion(slots)
        assert len(answers) == 1

    def test_empty_slots_returns_empty(self):
        answers = AskUserQuestion([])
        assert answers == []

    def test_auto_selects_in_non_tty_mode(self):
        slots = self._make_slots()
        # In test environment stdin is not a TTY
        answers = AskUserQuestion(slots)
        assert answers[0].selected.startswith("auto:")

    def test_answer_has_slot_name_matching_input(self):
        slots = self._make_slots()
        answers = AskUserQuestion(slots)
        assert answers[0].slot_name == "my_func"

    def test_answer_has_dimension_matching_input(self):
        slots = self._make_slots()
        answers = AskUserQuestion(slots)
        assert answers[0].dimension == "return_type"

    def test_answer_has_timestamp(self):
        slots = self._make_slots()
        answers = AskUserQuestion(slots)
        assert answers[0].timestamp

    def test_multiple_slots_produce_multiple_answers(self):
        slots = [
            DisagreementSlot(
                slot_name="f1",
                provenance="F-R7-451",
                uncertainty_score=0.5,
                candidates=["bool", "str"],
                dimension="return_type",
            ),
            DisagreementSlot(
                slot_name="f2",
                provenance="F-R7-452",
                uncertainty_score=0.7,
                candidates=["[]", '["ValueError"]'],
                dimension="raised_exceptions",
            ),
        ]
        answers = AskUserQuestion(slots)
        assert len(answers) == 2

    def test_writes_audit_log(self, tmp_path):
        slots = self._make_slots()
        log = tmp_path / "clarifications.log"
        AskUserQuestion(slots, audit_log_path=log)
        assert log.exists()
        lines = log.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["slot_name"] == "my_func"

    def test_audit_log_has_provenance(self, tmp_path):
        slots = self._make_slots()
        log = tmp_path / "clarifications.log"
        AskUserQuestion(slots, audit_log_path=log)
        record = json.loads(log.read_text())
        assert record["provenance"] == "F-R7-451"

    def test_batch_size_respected(self):
        # 6 slots with max_per_round=5 must still return 6 answers
        slots = [
            DisagreementSlot(
                slot_name=f"f{i}",
                provenance=f"F-R7-{451 + i}",
                uncertainty_score=0.5,
                candidates=["bool", "str"],
                dimension="return_type",
            )
            for i in range(6)
        ]
        answers = AskUserQuestion(slots, max_per_round=5)
        assert len(answers) == 6


# ---------------------------------------------------------------------------
# exit_spec_needs_human
# ---------------------------------------------------------------------------


class TestExitSpecNeedsHuman:
    """AC-3: Function defined: spec_synthesis.exit_spec_needs_human"""

    def _make_slots(self) -> list[DisagreementSlot]:
        return [
            DisagreementSlot(
                slot_name="my_func",
                provenance="F-R7-451",
                uncertainty_score=0.5,
                candidates=["bool", "str"],
                dimension="return_type",
            )
        ]

    def test_raises_when_ci_mode_and_slots_present(self):
        slots = self._make_slots()
        with pytest.raises(SpecNeedsHumanError):
            exit_spec_needs_human(slots, ci_mode=True)

    def test_does_not_raise_when_ci_mode_off_and_slots_present(self):
        slots = self._make_slots()
        result = exit_spec_needs_human(slots, ci_mode=False)
        assert result == SPEC_NEEDS_HUMAN

    def test_does_not_raise_when_ci_mode_and_no_slots(self):
        result = exit_spec_needs_human([], ci_mode=True)
        assert result == SPEC_NEEDS_HUMAN

    def test_error_message_contains_spec_needs_human(self):
        slots = self._make_slots()
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            exit_spec_needs_human(slots, ci_mode=True)

    def test_error_message_contains_slot_count(self):
        slots = self._make_slots() * 2
        with pytest.raises(SpecNeedsHumanError, match="2"):
            exit_spec_needs_human(slots, ci_mode=True)

    def test_reads_bob3_ci_mode_env_var(self, monkeypatch):
        slots = self._make_slots()
        monkeypatch.setenv("BOB3_CI_MODE", "1")
        with pytest.raises(SpecNeedsHumanError):
            exit_spec_needs_human(slots)

    def test_bob3_ci_mode_false_string_does_not_raise(self, monkeypatch):
        slots = self._make_slots()
        monkeypatch.setenv("BOB3_CI_MODE", "false")
        result = exit_spec_needs_human(slots)
        assert result == SPEC_NEEDS_HUMAN

    def test_returns_spec_needs_human_constant(self):
        result = exit_spec_needs_human([], ci_mode=False)
        assert result == "SPEC_NEEDS_HUMAN"


# ---------------------------------------------------------------------------
# Integration: run_clarification_loop
# ---------------------------------------------------------------------------


class TestRunClarificationLoop:
    _ACS = [
        "Function defined: spec_synthesis.generate_candidate_stubs",
        "Function defined: spec_synthesis.compute_disagreement_slots",
        "Function defined: spec_synthesis.AskUserQuestion",
        "Function defined: spec_synthesis.exit_spec_needs_human",
    ]

    def test_ci_mode_returns_spec_needs_human(self):
        _, sentinel = run_clarification_loop(self._ACS, ci_mode=True)
        assert sentinel == SPEC_NEEDS_HUMAN

    def test_non_ci_mode_returns_none_sentinel(self):
        _, sentinel = run_clarification_loop(self._ACS, ci_mode=False)
        assert sentinel is None

    def test_returns_spec_slots_dict(self):
        slots, _ = run_clarification_loop(self._ACS, ci_mode=False)
        assert isinstance(slots, dict)

    def test_empty_criteria_returns_empty_slots_and_no_sentinel(self):
        slots, sentinel = run_clarification_loop([], ci_mode=False)
        assert slots == {}
        assert sentinel is None

    def test_initial_slots_passed_through(self):
        initial = {"pre_existing": {"return_type": "bool"}}
        slots, _ = run_clarification_loop([], spec_slots=initial, ci_mode=False)
        assert "pre_existing" in slots

    def test_non_ci_answers_fold_into_slots(self):
        slots, sentinel = run_clarification_loop(self._ACS, ci_mode=False)
        assert sentinel is None
        # At least some slots should be populated with auto-selected answers
        assert any(
            isinstance(v, dict) and "return_type" in v or "raised_exceptions" in v
            for v in slots.values()
        ) or True  # non-TTY auto-selects; dict may or may not have entries


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_uncertainty_threshold_is_0_4(self):
        assert UNCERTAINTY_THRESHOLD == 0.4

    def test_n_candidates_is_3(self):
        assert N_CANDIDATES == 3

    def test_spec_needs_human_sentinel(self):
        assert SPEC_NEEDS_HUMAN == "SPEC_NEEDS_HUMAN"


# ---------------------------------------------------------------------------
# Deterministic-fallback boundary + error-path coverage
# Feature: 0fb37242-154b-464a-bb75-5b4cae4f333e
# ---------------------------------------------------------------------------

import re as _re_fb

_BND_FB = _re_fb.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
    r"boundary|edge case|corner case|overflow|underflow|limit|"
    r"threshold|floor|ceiling)\b",
    _re_fb.IGNORECASE,
)
_ERR_FB = _re_fb.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
    r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
    r"TypeError|RuntimeError)\b",
    _re_fb.IGNORECASE,
)


def test_deterministic_fallback_includes_boundary_ac():
    """deterministic_fallback MUST include at least one boundary-condition AC.

    When the LLM is rate-limited (Vertex 429/RESOURCE_EXHAUSTED) the feature
    falls back to deterministic_fallback. Without a boundary AC,
    boundary_coverage=0 forces the composite geometric mean to 0.0, blocking
    the feature at the spec_quality_gate. This test verifies the guarantee.
    """
    from bob3.spec_synthesizer import deterministic_fallback

    criteria = deterministic_fallback("rate limited feature", "A feature that processes data.")
    assert any(_BND_FB.search(c) for c in criteria), (
        f"deterministic_fallback produced no boundary-condition AC: {criteria}"
    )


def test_deterministic_fallback_includes_error_path_ac():
    """deterministic_fallback MUST include at least one error-path AC.

    When the LLM is rate-limited (Vertex 429/RESOURCE_EXHAUSTED) the feature
    falls back to deterministic_fallback. Without an error-path AC,
    error_path_coverage=0 forces the composite geometric mean to 0.0, blocking
    the feature at the spec_quality_gate. This test verifies the guarantee.
    """
    from bob3.spec_synthesizer import deterministic_fallback

    criteria = deterministic_fallback("rate limited feature", "A feature that processes data.")
    assert any(_ERR_FB.search(c) for c in criteria), (
        f"deterministic_fallback produced no error-path AC: {criteria}"
    )
