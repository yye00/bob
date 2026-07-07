"""Tests for feature dc3b4168-a0b6-4404-b3c6-118527993f1d.

Rename ALL_BLOCKED termination label to QUEUE_DRAINED in the run-finished
log line and provide a clearer user-facing CLI message.

Semantics: ``ALL_BLOCKED`` means "the ready queue is empty — the orchestrator
has nothing eligible to claim and exits cleanly", NOT a stuck/failure state.
The enum *value* (``all_blocked``) is unchanged to preserve DB/serialisation
compatibility; only the user-visible label and log token change.
"""
from __future__ import annotations

import logging

import pytest


def _make_orch():
    """Build a minimal OrchestrationLoop instance without running __init__."""
    from bob.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


# ---------------------------------------------------------------------------
# Enum value is preserved (DB / serialisation compatibility)
# ---------------------------------------------------------------------------


def test_enum_value_unchanged():
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"
    assert LoopTermination.ALL_BLOCKED.name == "ALL_BLOCKED"


# ---------------------------------------------------------------------------
# translate_termination_label helper
# ---------------------------------------------------------------------------


def test_translate_all_blocked_to_queue_drained():
    from bob.orchestrator.run_loop import translate_termination_label

    assert translate_termination_label("ALL_BLOCKED") == "QUEUE_DRAINED"


def test_translate_passthrough_for_other_labels():
    from bob.orchestrator.run_loop import translate_termination_label

    for name in ("ALL_COMPLETED", "BUDGET_EXCEEDED", "SHUTDOWN_REQUESTED", "RAISED"):
        assert translate_termination_label(name) == name


# ---------------------------------------------------------------------------
# format_termination_message helper
# ---------------------------------------------------------------------------


def test_format_termination_message_all_blocked():
    from bob.orchestrator.run_loop import (
        LoopTermination,
        format_termination_message,
    )

    assert format_termination_message(LoopTermination.ALL_BLOCKED) == "QUEUE_DRAINED"


def test_format_termination_message_none_is_raised():
    from bob.orchestrator.run_loop import format_termination_message

    assert format_termination_message(None) == "RAISED"


def test_format_termination_message_other_members():
    from bob.orchestrator.run_loop import (
        LoopTermination,
        format_termination_message,
    )

    assert format_termination_message(LoopTermination.ALL_COMPLETED) == "ALL_COMPLETED"
    assert (
        format_termination_message(LoopTermination.BUDGET_EXCEEDED)
        == "BUDGET_EXCEEDED"
    )


# ---------------------------------------------------------------------------
# Log line uses the translated token
# ---------------------------------------------------------------------------


def test_run_finished_log_uses_queue_drained(caplog):
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "Run finished:" in combined
    assert "termination=QUEUE_DRAINED" in combined
    assert "termination=ALL_BLOCKED" not in combined


def test_run_finished_log_other_terminations_untranslated(caplog):
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_COMPLETED)

    combined = " ".join(caplog.messages)
    assert "termination=ALL_COMPLETED" in combined
    assert "QUEUE_DRAINED" not in combined


# ---------------------------------------------------------------------------
# CLI user-facing message
# ---------------------------------------------------------------------------


def test_cli_queue_drained_message():
    from bob.cli import format_queue_drained_message

    msg = format_queue_drained_message()
    assert "Queue drained" in msg
    assert "no ready features left to claim" in msg
    assert "needs_human" in msg
    assert "executing" in msg
    assert "blocked" in msg


def test_cli_main_defined():
    from bob.cli import main

    assert callable(main)


def test_run_loop_defined():
    from bob.orchestrator.run_loop import run_loop

    assert callable(run_loop)
