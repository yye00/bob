"""Tests that exit_spec_needs_human_in_ci raises CIClarificationRequiredError.

Feature: 88ed1561-6477-4508-b7a6-08e64aa89b84
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.clarification_loop import (
    CIClarificationRequiredError,
    SlotUncertainty,
    exit_spec_needs_human_in_ci,
)


def _make_slot(name: str = "ambig_func") -> SlotUncertainty:
    return SlotUncertainty(
        slot_name=name,
        provenance="F-R7-451",
        uncertainty_score=0.75,
        candidates=["bool", "None"],
        dimension="return_type",
    )


class TestExitSpecNeedsHumanInCi:
    def test_raises_when_ci_and_uncertain_slots_non_empty(self):
        with pytest.raises(CIClarificationRequiredError):
            exit_spec_needs_human_in_ci([_make_slot()], ci_mode=True)

    def test_no_raise_when_not_ci_even_with_slots(self):
        exit_spec_needs_human_in_ci([_make_slot()], ci_mode=False)

    def test_no_raise_when_ci_but_no_slots(self):
        exit_spec_needs_human_in_ci([], ci_mode=True)

    def test_no_raise_when_not_ci_no_slots(self):
        exit_spec_needs_human_in_ci([], ci_mode=False)

    def test_error_message_contains_spec_needs_human(self):
        with pytest.raises(CIClarificationRequiredError, match="SPEC_NEEDS_HUMAN"):
            exit_spec_needs_human_in_ci([_make_slot()], ci_mode=True)

    def test_error_message_mentions_slot_count(self):
        slots = [_make_slot(f"func_{i}") for i in range(3)]
        with pytest.raises(CIClarificationRequiredError, match="3"):
            exit_spec_needs_human_in_ci(slots, ci_mode=True)

    def test_env_var_ci_mode_triggers_raise(self, monkeypatch):
        monkeypatch.setenv("BOB3_CI_MODE", "1")
        with pytest.raises(CIClarificationRequiredError):
            exit_spec_needs_human_in_ci([_make_slot()])

    def test_env_var_ci_mode_false_no_raise(self, monkeypatch):
        monkeypatch.setenv("BOB3_CI_MODE", "0")
        exit_spec_needs_human_in_ci([_make_slot()])

    def test_env_var_unset_no_raise(self, monkeypatch):
        monkeypatch.delenv("BOB3_CI_MODE", raising=False)
        exit_spec_needs_human_in_ci([_make_slot()])

    def test_ci_clarification_required_error_is_runtime_error(self):
        assert issubclass(CIClarificationRequiredError, RuntimeError)

    def test_error_message_mentions_slot_names(self):
        with pytest.raises(CIClarificationRequiredError, match="ambig_func"):
            exit_spec_needs_human_in_ci([_make_slot("ambig_func")], ci_mode=True)
