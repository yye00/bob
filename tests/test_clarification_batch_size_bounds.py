"""Tests for batch size bounds (1-5 questions per round) in ask_user_batched.

Feature: 88ed1561-6477-4508-b7a6-08e64aa89b84
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.clarification_loop import (
    MAX_QUESTIONS_PER_ROUND,
    SlotUncertainty,
    ask_user_batched,
)


def _make_slots(n: int) -> list[SlotUncertainty]:
    return [
        SlotUncertainty(
            slot_name=f"func_{i}",
            provenance=f"F-R7-{451 + i}",
            uncertainty_score=0.6,
            candidates=["bool", "None", "str"],
            dimension="return_type",
        )
        for i in range(n)
    ]


class TestBatchSizeBounds:
    def test_max_questions_per_round_constant(self):
        assert MAX_QUESTIONS_PER_ROUND == 5

    def test_single_slot_returns_one_answer(self, tmp_path):
        slots = _make_slots(1)
        answers = ask_user_batched(slots, max_per_round=5, audit_log_path=tmp_path / "cl.log")
        assert len(answers) == 1

    def test_five_slots_returns_five_answers(self, tmp_path):
        slots = _make_slots(5)
        answers = ask_user_batched(slots, max_per_round=5, audit_log_path=tmp_path / "cl.log")
        assert len(answers) == 5

    def test_six_slots_two_batches_all_answered(self, tmp_path):
        # 6 slots with max_per_round=5 → two batches (5 + 1), all answered
        slots = _make_slots(6)
        answers = ask_user_batched(slots, max_per_round=5, audit_log_path=tmp_path / "cl.log")
        assert len(answers) == 6

    def test_max_per_round_one_all_answered(self, tmp_path):
        slots = _make_slots(3)
        answers = ask_user_batched(slots, max_per_round=1, audit_log_path=tmp_path / "cl.log")
        assert len(answers) == 3

    def test_empty_slots_returns_empty_answers(self, tmp_path):
        answers = ask_user_batched([], max_per_round=5, audit_log_path=tmp_path / "cl.log")
        assert answers == []

    def test_ten_slots_all_answered(self, tmp_path):
        slots = _make_slots(10)
        answers = ask_user_batched(slots, max_per_round=5, audit_log_path=tmp_path / "cl.log")
        assert len(answers) == 10

    def test_answers_match_slot_order(self, tmp_path):
        slots = _make_slots(3)
        answers = ask_user_batched(slots, max_per_round=5, audit_log_path=tmp_path / "cl.log")
        for i, (slot, answer) in enumerate(zip(slots, answers)):
            assert answer.slot_name == slot.slot_name, (
                f"Answer {i} slot_name mismatch: expected {slot.slot_name!r}, got {answer.slot_name!r}"
            )

    def test_batch_audit_log_records_all(self, tmp_path):
        log_path = tmp_path / "cl.log"
        n = 7
        slots = _make_slots(n)
        ask_user_batched(slots, max_per_round=5, audit_log_path=log_path)
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == n
