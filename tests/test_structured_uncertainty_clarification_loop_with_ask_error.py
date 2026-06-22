"""Error-path tests for spec_synthesis.uncertainty_loop.

Feature: 727ecb70-297d-4ca0-a774-f585e13821c6
AC: invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from spec_synthesis.uncertainty_loop import (
    compute_disagreement_slots,
    generate_candidate_stubs,
    trigger_clarification_questions,
)
from spec_synthesis import CandidateStub, DisagreementSlot, SpecNeedsHumanError


# ---------------------------------------------------------------------------
# generate_candidate_stubs — error paths
# ---------------------------------------------------------------------------


class TestGenerateCandidateStubsErrors:
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
            generate_candidate_stubs("not a list")  # type: ignore[arg-type]

    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs(None)  # type: ignore[arg-type]

    def test_dict_input_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs({"key": "value"})  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises(ValueError, match="items must be strings"):
            generate_candidate_stubs([123, "Function defined: foo.bar"])  # type: ignore[arg-type]

    def test_list_with_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_candidate_stubs([None])  # type: ignore[arg-type]

    def test_n_candidates_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(
                ["Function defined: foo.bar"],
                n_candidates=0,
            )

    def test_n_candidates_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="n_candidates must be >= 1"):
            generate_candidate_stubs(
                ["Function defined: foo.bar"],
                n_candidates=-1,
            )


# ---------------------------------------------------------------------------
# compute_disagreement_slots — error paths
# ---------------------------------------------------------------------------


class TestComputeDisagreementSlotsErrors:
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="stubs must be a list"):
            compute_disagreement_slots("not a list")  # type: ignore[arg-type]

    def test_none_stubs_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_disagreement_slots(None)  # type: ignore[arg-type]

    def test_threshold_below_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_disagreement_slots([], threshold=-0.1)

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            compute_disagreement_slots([], threshold=1.1)

    def test_threshold_negative_large_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_disagreement_slots([], threshold=-999.0)


# ---------------------------------------------------------------------------
# trigger_clarification_questions — error paths
# ---------------------------------------------------------------------------


class TestTriggerClarificationQuestionsErrors:
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="disagreement_slots must be a list"):
            trigger_clarification_questions("not a list")  # type: ignore[arg-type]

    def test_none_slots_raises_value_error(self):
        with pytest.raises(ValueError):
            trigger_clarification_questions(None)  # type: ignore[arg-type]

    def test_max_per_round_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_clarification_questions([], max_per_round=0)

    def test_max_per_round_six_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_clarification_questions([], max_per_round=6)

    def test_max_per_round_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="max_per_round"):
            trigger_clarification_questions([], max_per_round=-1)

    def test_ci_mode_with_ambiguous_slots_raises_spec_needs_human(self):
        """CI mode + non-empty slots raises SpecNeedsHumanError (not silently succeeds)."""
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=1.0,
            candidates=["bool", "int", "str"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError):
            trigger_clarification_questions([slot], ci_mode=True)

    def test_ci_mode_error_message_contains_spec_needs_human(self):
        """SpecNeedsHumanError message includes SPEC_NEEDS_HUMAN sentinel."""
        slot = DisagreementSlot(
            slot_name="my_func",
            provenance="F-R7-451",
            uncertainty_score=0.9,
            candidates=["bool", "None"],
            dimension="return_type",
        )
        with pytest.raises(SpecNeedsHumanError, match="SPEC_NEEDS_HUMAN"):
            trigger_clarification_questions([slot], ci_mode=True)

    def test_ci_mode_does_not_silently_return_wrong_answer(self):
        """Ensure CI mode never returns answers when slots are ambiguous."""
        slot = DisagreementSlot(
            slot_name="risky_func",
            provenance="F-R7-999",
            uncertainty_score=0.8,
            candidates=["A", "B"],
            dimension="return_type",
        )
        raised = False
        try:
            trigger_clarification_questions([slot], ci_mode=True)
        except SpecNeedsHumanError:
            raised = True
        assert raised, "Expected SpecNeedsHumanError but no exception was raised"
