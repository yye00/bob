"""Tests for the translate_termination_label function in bob3.orchestrator.run_loop.

Verifies that ALL_BLOCKED → QUEUE_DRAINED translation works correctly
while preserving DB/serialisation compatibility (enum value unchanged).
"""
from __future__ import annotations

import logging

import pytest

from bob3.orchestrator.run_loop import (
    LoopTermination,
    format_termination_message,
    translate_termination_label,
)


class TestTranslateTerminationLabel:
    def test_all_blocked_translates_to_queue_drained(self):
        assert translate_termination_label("ALL_BLOCKED") == "QUEUE_DRAINED"

    def test_all_completed_unchanged(self):
        assert translate_termination_label("ALL_COMPLETED") == "ALL_COMPLETED"

    def test_budget_exceeded_unchanged(self):
        assert translate_termination_label("BUDGET_EXCEEDED") == "BUDGET_EXCEEDED"

    def test_shutdown_requested_unchanged(self):
        assert translate_termination_label("SHUTDOWN_REQUESTED") == "SHUTDOWN_REQUESTED"

    def test_arbitrary_string_unchanged(self):
        assert translate_termination_label("SOME_OTHER") == "SOME_OTHER"

    def test_empty_string_unchanged(self):
        assert translate_termination_label("") == ""

    def test_case_sensitive_only_all_caps_translates(self):
        # Lowercase "all_blocked" (the enum VALUE) must NOT be translated
        assert translate_termination_label("all_blocked") == "all_blocked"


class TestFormatTerminationMessage:
    def test_all_blocked_formats_as_queue_drained(self):
        assert format_termination_message(LoopTermination.ALL_BLOCKED) == "QUEUE_DRAINED"

    def test_all_completed_formats_as_all_completed(self):
        assert format_termination_message(LoopTermination.ALL_COMPLETED) == "ALL_COMPLETED"

    def test_budget_exceeded_formats_as_budget_exceeded(self):
        assert format_termination_message(LoopTermination.BUDGET_EXCEEDED) == "BUDGET_EXCEEDED"

    def test_none_formats_as_raised(self):
        assert format_termination_message(None) == "RAISED"


class TestLoopTerminationEnumCompat:
    def test_all_blocked_value_unchanged(self):
        """Enum VALUE must not be renamed — DB/serialisation compat."""
        assert LoopTermination.ALL_BLOCKED.value == "all_blocked"

    def test_all_blocked_name_unchanged(self):
        """Enum NAME must remain ALL_BLOCKED."""
        assert LoopTermination.ALL_BLOCKED.name == "ALL_BLOCKED"

    def test_all_completed_value_unchanged(self):
        assert LoopTermination.ALL_COMPLETED.value == "all_completed"

    def test_budget_exceeded_value_unchanged(self):
        assert LoopTermination.BUDGET_EXCEEDED.value == "budget_exceeded"

    def test_shutdown_requested_value_unchanged(self):
        assert LoopTermination.SHUTDOWN_REQUESTED.value == "shutdown_requested"


class TestEmitRunSummaryLog:
    def _make_orch(self):
        from bob3.orchestrator.run_loop import OrchestrationLoop

        orch = OrchestrationLoop.__new__(OrchestrationLoop)
        orch._run_start_time = None
        orch._project_total_cost = 0.0
        orch.features_completed = 0
        orch.features_failed = 0
        orch._refresh_project_cost_cache = lambda: None
        return orch

    def test_all_blocked_logs_queue_drained(self, caplog):
        orch = self._make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_BLOCKED)
        combined = " ".join(caplog.messages)
        assert "QUEUE_DRAINED" in combined

    def test_all_blocked_does_not_log_all_blocked_token(self, caplog):
        orch = self._make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_BLOCKED)
        for msg in caplog.messages:
            assert "termination=ALL_BLOCKED" not in msg

    def test_all_completed_logs_all_completed(self, caplog):
        orch = self._make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_COMPLETED)
        combined = " ".join(caplog.messages)
        assert "ALL_COMPLETED" in combined

    def test_none_termination_logs_raised(self, caplog):
        orch = self._make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(None)
        combined = " ".join(caplog.messages)
        assert "RAISED" in combined

    def test_log_line_starts_with_run_finished(self, caplog):
        orch = self._make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_BLOCKED)
        assert any("Run finished:" in m for m in caplog.messages)
