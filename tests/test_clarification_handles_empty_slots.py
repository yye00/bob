"""Tests that ask_user_batched returns empty list when no slots are above threshold.

Feature: 88ed1561-6477-4508-b7a6-08e64aa89b84
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob.spec_quality.clarification_loop import (
    UNCERTAINTY_THRESHOLD,
    SlotUncertainty,
    ask_user_batched,
    handle_empty_slots,
)


class TestHandleEmptySlots:
    def test_handle_empty_slots_returns_empty_list(self):
        result = handle_empty_slots([])
        assert result == []

    def test_handle_empty_slots_returns_list_type(self):
        result = handle_empty_slots([])
        assert isinstance(result, list)

    def test_handle_empty_slots_with_non_empty_raises(self):
        slot = SlotUncertainty(
            slot_name="func_x",
            provenance="F-R7-451",
            uncertainty_score=0.8,
            candidates=["bool", "None"],
            dimension="return_type",
        )
        with pytest.raises(ValueError, match="handle_empty_slots"):
            handle_empty_slots([slot])

    def test_ask_user_batched_empty_slots_returns_empty(self, tmp_path):
        answers = ask_user_batched([], audit_log_path=tmp_path / "cl.log")
        assert answers == []

    def test_ask_user_batched_empty_creates_no_log_entries(self, tmp_path):
        log_path = tmp_path / "cl.log"
        ask_user_batched([], audit_log_path=log_path)
        if log_path.exists():
            lines = [l for l in log_path.read_text().splitlines() if l.strip()]
            assert lines == []

    def test_slots_below_threshold_produce_no_uncertain_slots(self):
        from bob.spec_quality.clarification_loop import code_consistency_check

        # File exists ACs produce no function stubs → no uncertain slots
        acs = ["File exists: src/bob/spec_quality/clarification_loop.py"]
        report = code_consistency_check(acs, ci_mode=False)
        assert report.uncertain_slots == []

    def test_handle_empty_slots_idempotent(self):
        r1 = handle_empty_slots([])
        r2 = handle_empty_slots([])
        assert r1 == r2 == []
