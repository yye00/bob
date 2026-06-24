"""Tests that clarification questions are triggered only for slots above threshold T=0.4.

Feature: e38b904e-6b04-4d5a-818b-095c0f3a26be
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob.spec_quality.clarification_loop import (
    UNCERTAINTY_THRESHOLD,
    code_consistency_check,
    compute_slot_uncertainty,
)


class TestComputeSlotUncertainty:
    def test_all_same_returns_zero(self):
        values = ["bool", "bool", "bool"]
        assert compute_slot_uncertainty(values) == 0.0

    def test_all_different_returns_one(self):
        values = ["bool", "str", "int"]
        score = compute_slot_uncertainty(values)
        assert score == 1.0

    def test_two_of_three_different(self):
        values = ["bool", "str", "bool"]
        score = compute_slot_uncertainty(values)
        # 2 distinct, n=3: (2-1)/(3-1) = 0.5
        assert score == pytest.approx(0.5)

    def test_single_element_returns_zero(self):
        assert compute_slot_uncertainty(["bool"]) == 0.0

    def test_empty_list_returns_zero(self):
        assert compute_slot_uncertainty([]) == 0.0

    def test_two_elements_all_same(self):
        assert compute_slot_uncertainty(["X", "X"]) == 0.0

    def test_two_elements_all_different(self):
        assert compute_slot_uncertainty(["X", "Y"]) == 1.0

    def test_uncertainty_threshold_constant(self):
        assert UNCERTAINTY_THRESHOLD == 0.4


class TestCodeConsistencyCheckThreshold:
    """Verify only slots above T=0.4 appear in uncertain_slots."""

    def _ac_list_with_funcs(self):
        return [
            "File exists: src/bob/spec_quality/clarification_loop.py",
            "Function defined: bob.spec_quality.clarification_loop.code_consistency_check",
            "Function defined: bob.spec_quality.clarification_loop.compute_slot_uncertainty",
            "Function defined: bob.spec_quality.clarification_loop.ask_user_batched",
            "Function defined: bob.spec_quality.clarification_loop.fold_answer_into_slot",
        ]

    def test_uncertain_slots_have_scores_above_threshold(self):
        report = code_consistency_check(self._ac_list_with_funcs(), ci_mode=False)
        for slot in report.uncertain_slots:
            assert slot.uncertainty_score > UNCERTAINTY_THRESHOLD, (
                f"Slot {slot.slot_name}.{slot.dimension} score "
                f"{slot.uncertainty_score} should be > {UNCERTAINTY_THRESHOLD}"
            )

    def test_stubs_are_generated_per_slot(self):
        report = code_consistency_check(self._ac_list_with_funcs(), ci_mode=False)
        # We should get N_STUBS stubs per function slot
        assert len(report.stubs) > 0

    def test_report_has_stubs_and_uncertain_slots(self):
        report = code_consistency_check(self._ac_list_with_funcs(), ci_mode=False)
        assert isinstance(report.stubs, list)
        assert isinstance(report.uncertain_slots, list)

    def test_empty_criteria_produces_no_uncertain_slots(self):
        report = code_consistency_check([], ci_mode=False)
        assert report.uncertain_slots == []
        assert report.stubs == []

    def test_file_exists_ac_not_extracted_as_slot(self):
        # "File exists:" ACs should not generate function stubs
        acs = ["File exists: src/bob/spec_quality/clarification_loop.py"]
        report = code_consistency_check(acs, ci_mode=False)
        # File exists creates no function-level stubs
        assert report.stubs == []

    def test_uncertain_slots_have_candidates(self):
        report = code_consistency_check(self._ac_list_with_funcs(), ci_mode=False)
        for slot in report.uncertain_slots:
            assert len(slot.candidates) >= 2, (
                f"Slot {slot.slot_name}.{slot.dimension} should have >= 2 candidates"
            )

    def test_uncertain_slots_have_provenance(self):
        report = code_consistency_check(self._ac_list_with_funcs(), ci_mode=False)
        for slot in report.uncertain_slots:
            assert slot.provenance.startswith("F-R7-"), (
                f"Slot provenance should start with 'F-R7-', got {slot.provenance!r}"
            )

    def test_n_stubs_parameter_respected(self):
        acs = [
            "Function defined: bob.spec_quality.clarification_loop.code_consistency_check",
        ]
        report = code_consistency_check(acs, n_stubs=2, ci_mode=False)
        # With n=2 stubs per slot, total stubs should be 2
        assert len(report.stubs) == 2
