"""Tests that the clarification audit log records every (timestamp, question, choices, selection).

Feature: e38b904e-6b04-4d5a-818b-095c0f3a26be
Spec: Structured-uncertainty clarification loop with AskUserQuestion
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob.spec_quality.clarification_loop import (
    ClarificationAnswer,
    ClarificationQuestion,
    SlotUncertainty,
    ask_user_batched,
    fold_answer_into_slot,
    _append_audit_log,
    _build_questions,
)


def _make_uncertain_slots(n: int = 2) -> list[SlotUncertainty]:
    return [
        SlotUncertainty(
            slot_name=f"my_func_{i}",
            provenance=f"F-R7-{451 + i}",
            uncertainty_score=0.5 + i * 0.1,
            candidates=["bool", "None", "dict[str, Any]"],
            dimension="return_type",
        )
        for i in range(n)
    ]


class TestAuditLogRecordsInteraction:
    def test_audit_log_created(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        # Non-TTY: auto-selects first candidate
        ask_user_batched(slots, audit_log_path=log_path)
        assert log_path.exists()

    def test_audit_log_has_one_line_per_question(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        n = 3
        slots = _make_uncertain_slots(n)
        ask_user_batched(slots, audit_log_path=log_path)
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == n

    def test_audit_log_entries_are_valid_json(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(2)
        ask_user_batched(slots, audit_log_path=log_path)
        for line in log_path.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                assert isinstance(record, dict)

    def test_audit_log_entry_has_required_fields(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        ask_user_batched(slots, audit_log_path=log_path)
        record = json.loads(log_path.read_text().strip().splitlines()[0])
        required = {"timestamp", "slot_name", "dimension", "provenance", "question", "choices", "selection"}
        assert required <= record.keys(), f"Missing fields: {required - record.keys()}"

    def test_audit_log_records_timestamp(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        ask_user_batched(slots, audit_log_path=log_path)
        record = json.loads(log_path.read_text().strip())
        assert record["timestamp"]
        # Must be ISO-8601 compatible (contains T and Z or +)
        assert "T" in record["timestamp"]

    def test_audit_log_records_choices(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        ask_user_batched(slots, audit_log_path=log_path)
        record = json.loads(log_path.read_text().strip())
        assert isinstance(record["choices"], list)
        assert len(record["choices"]) >= 2
        assert "Other" in record["choices"]

    def test_audit_log_records_selection(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        ask_user_batched(slots, audit_log_path=log_path)
        record = json.loads(log_path.read_text().strip())
        assert record["selection"]  # non-empty string

    def test_audit_log_records_provenance(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        ask_user_batched(slots, audit_log_path=log_path)
        record = json.loads(log_path.read_text().strip())
        assert record["provenance"].startswith("F-R7-")

    def test_audit_log_appends_across_calls(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        ask_user_batched(slots, audit_log_path=log_path)
        ask_user_batched(slots, audit_log_path=log_path)
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_batch_size_respected(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(6)
        answers = ask_user_batched(slots, max_per_round=5, audit_log_path=log_path)
        assert len(answers) == 6

    def test_auto_selection_in_non_tty_prefix(self, tmp_path):
        log_path = tmp_path / "clarifications.log"
        slots = _make_uncertain_slots(1)
        answers = ask_user_batched(slots, audit_log_path=log_path)
        # In non-TTY mode (CI), selected starts with "auto:"
        assert answers[0].selected.startswith("auto:")


class TestFoldAnswerIntoSlot:
    def test_fold_populates_dimension(self):
        spec_slots: dict = {}
        answer = ClarificationAnswer(
            slot_name="my_func",
            dimension="return_type",
            selected="bool",
            timestamp="2026-05-24T00:00:00+00:00",
        )
        result = fold_answer_into_slot(spec_slots, answer)
        assert result["my_func"]["return_type"] == "bool"

    def test_fold_sets_clarified_at(self):
        spec_slots: dict = {}
        answer = ClarificationAnswer(
            slot_name="my_func",
            dimension="return_type",
            selected="bool",
            timestamp="2026-05-24T00:00:00+00:00",
        )
        fold_answer_into_slot(spec_slots, answer)
        assert spec_slots["my_func"]["_clarified_at"] == "2026-05-24T00:00:00+00:00"

    def test_fold_preserves_existing_dimensions(self):
        spec_slots: dict = {"my_func": {"raised_exceptions": "ValueError"}}
        answer = ClarificationAnswer(
            slot_name="my_func",
            dimension="return_type",
            selected="None",
            timestamp="2026-05-24T00:00:00+00:00",
        )
        fold_answer_into_slot(spec_slots, answer)
        assert spec_slots["my_func"]["raised_exceptions"] == "ValueError"
        assert spec_slots["my_func"]["return_type"] == "None"

    def test_fold_multiple_answers(self):
        spec_slots: dict = {}
        for dim, val in [("return_type", "bool"), ("raised_exceptions", "ValueError")]:
            answer = ClarificationAnswer(
                slot_name="my_func",
                dimension=dim,
                selected=val,
                timestamp="2026-05-24T00:00:00+00:00",
            )
            fold_answer_into_slot(spec_slots, answer)
        assert spec_slots["my_func"]["return_type"] == "bool"
        assert spec_slots["my_func"]["raised_exceptions"] == "ValueError"

    def test_fold_returns_updated_dict(self):
        spec_slots: dict = {}
        answer = ClarificationAnswer(
            slot_name="my_func",
            dimension="return_type",
            selected="bool",
            timestamp="2026-05-24T00:00:00+00:00",
        )
        result = fold_answer_into_slot(spec_slots, answer)
        assert result is spec_slots
