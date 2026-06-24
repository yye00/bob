"""Tests for ALL_BLOCKED → QUEUE_DRAINED termination label rename.

Verifies that:
- translate_termination_label maps ALL_BLOCKED to QUEUE_DRAINED
- format_termination_message returns QUEUE_DRAINED for ALL_BLOCKED
- _emit_run_summary logs QUEUE_DRAINED, not ALL_BLOCKED
- CLI carries the correct user-facing message
- Enum value remains unchanged for DB/serialization compat
"""
from __future__ import annotations

import logging

import pytest

from bob.orchestrator.run_loop import (
    LoopTermination,
    format_termination_message,
    translate_termination_label,
)


def _make_orch():
    from bob.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


class TestTranslateTerminationLabel:
    def test_all_blocked_maps_to_queue_drained(self):
        assert translate_termination_label("ALL_BLOCKED") == "QUEUE_DRAINED"

    def test_all_completed_unchanged(self):
        assert translate_termination_label("ALL_COMPLETED") == "ALL_COMPLETED"

    def test_budget_exceeded_unchanged(self):
        assert translate_termination_label("BUDGET_EXCEEDED") == "BUDGET_EXCEEDED"

    def test_shutdown_requested_unchanged(self):
        assert translate_termination_label("SHUTDOWN_REQUESTED") == "SHUTDOWN_REQUESTED"

    def test_lowercase_all_blocked_not_translated(self):
        # The enum VALUE "all_blocked" must not be affected — only the NAME
        assert translate_termination_label("all_blocked") == "all_blocked"

    def test_arbitrary_string_passthrough(self):
        assert translate_termination_label("UNKNOWN_LABEL") == "UNKNOWN_LABEL"


class TestFormatTerminationMessage:
    def test_all_blocked_returns_queue_drained(self):
        assert format_termination_message(LoopTermination.ALL_BLOCKED) == "QUEUE_DRAINED"

    def test_all_completed_returns_all_completed(self):
        assert format_termination_message(LoopTermination.ALL_COMPLETED) == "ALL_COMPLETED"

    def test_budget_exceeded_returns_budget_exceeded(self):
        assert format_termination_message(LoopTermination.BUDGET_EXCEEDED) == "BUDGET_EXCEEDED"

    def test_none_returns_raised(self):
        assert format_termination_message(None) == "RAISED"


class TestEnumValuePreservation:
    def test_all_blocked_value_is_all_blocked(self):
        """Enum VALUE must stay 'all_blocked' for DB/serialization compat."""
        assert LoopTermination.ALL_BLOCKED.value == "all_blocked"

    def test_all_blocked_name_is_all_blocked(self):
        assert LoopTermination.ALL_BLOCKED.name == "ALL_BLOCKED"

    def test_value_is_not_queue_drained(self):
        assert LoopTermination.ALL_BLOCKED.value != "queue_drained"


class TestEmitRunSummaryLogsQueueDrained:
    def test_all_blocked_emits_queue_drained_token(self, caplog):
        orch = _make_orch()
        with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_BLOCKED)
        combined = " ".join(caplog.messages)
        assert "QUEUE_DRAINED" in combined

    def test_all_blocked_does_not_emit_old_token(self, caplog):
        orch = _make_orch()
        with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_BLOCKED)
        for msg in caplog.messages:
            assert "termination=ALL_BLOCKED" not in msg

    def test_log_contains_run_finished_prefix(self, caplog):
        orch = _make_orch()
        with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_BLOCKED)
        assert any("Run finished:" in m for m in caplog.messages)

    def test_all_completed_logs_all_completed_not_queue_drained(self, caplog):
        orch = _make_orch()
        with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
            orch._emit_run_summary(LoopTermination.ALL_COMPLETED)
        combined = " ".join(caplog.messages)
        assert "ALL_COMPLETED" in combined
        assert "QUEUE_DRAINED" not in combined


class TestCLIMessage:
    def test_cli_has_queue_drained_message_for_all_blocked(self):
        import bob.cli as cli_module
        import inspect

        source = inspect.getsource(cli_module)
        assert "Queue drained" in source

    def test_cli_does_not_have_deprecated_message(self):
        import bob.cli as cli_module
        import inspect

        source = inspect.getsource(cli_module)
        assert "All remaining features are blocked" not in source
