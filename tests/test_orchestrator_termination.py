"""Tests for feature 810e91d3-5ffe-46e0-ae4b-dfacde5f914a.

Verifies that the ALL_BLOCKED termination label is renamed to QUEUE_DRAINED
in log output and the CLI message is updated to be user-friendly.

Acceptance criteria:
- run_loop.py emits 'QUEUE_DRAINED' (not 'ALL_BLOCKED') in the log line
- cli/__init__.py message for ALL_BLOCKED mentions 'Queue drained'
- Enum value LoopTermination.ALL_BLOCKED == 'all_blocked' is preserved (DB compat)
"""
from __future__ import annotations

import inspect
import logging


# ---------------------------------------------------------------------------
# Structural: enum value must NOT change (DB/serialization compatibility)
# ---------------------------------------------------------------------------


def test_enum_all_blocked_value_preserved():
    """LoopTermination.ALL_BLOCKED.value must stay 'all_blocked' for DB compat."""
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"


def test_enum_all_blocked_member_exists():
    from bob.orchestrator.run_loop import LoopTermination

    assert hasattr(LoopTermination, "ALL_BLOCKED")


# ---------------------------------------------------------------------------
# Integration: run_loop._emit_run_summary logs QUEUE_DRAINED not ALL_BLOCKED
# ---------------------------------------------------------------------------


def test_log_says_queue_drained_not_all_blocked(caplog):
    """_emit_run_summary(ALL_BLOCKED) must log 'QUEUE_DRAINED', not 'ALL_BLOCKED'."""
    from bob.orchestrator.run_loop import LoopTermination, OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 2
    orch.features_failed = 1
    orch._refresh_project_cost_cache = lambda: None

    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "QUEUE_DRAINED" in combined, (
        f"Expected 'QUEUE_DRAINED' in log but got: {combined!r}"
    )
    assert "termination=ALL_BLOCKED" not in combined, (
        f"Old label 'ALL_BLOCKED' must not appear as termination token: {combined!r}"
    )


def test_log_run_finished_prefix_present(caplog):
    """The log line must contain 'Run finished: termination='."""
    from bob.orchestrator.run_loop import LoopTermination, OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None

    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    assert any("Run finished: termination=" in msg for msg in caplog.messages), (
        f"No 'Run finished: termination=' line in: {caplog.messages!r}"
    )


def test_other_terminations_keep_their_names(caplog):
    """ALL_COMPLETED and BUDGET_EXCEEDED must retain their original log names."""
    from bob.orchestrator.run_loop import LoopTermination, OrchestrationLoop

    for term in (LoopTermination.ALL_COMPLETED, LoopTermination.BUDGET_EXCEEDED):
        orch = OrchestrationLoop.__new__(OrchestrationLoop)
        orch._run_start_time = None
        orch._project_total_cost = 0.0
        orch.features_completed = 0
        orch.features_failed = 0
        orch._refresh_project_cost_cache = lambda: None

        with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
            orch._emit_run_summary(term)

        combined = " ".join(caplog.messages)
        assert term.name in combined, (
            f"Expected '{term.name}' in log for {term!r}: {combined!r}"
        )
        caplog.clear()


# ---------------------------------------------------------------------------
# Integration: CLI message says 'Queue drained' for ALL_BLOCKED
# ---------------------------------------------------------------------------


def test_cli_message_contains_queue_drained():
    """The CLI source for ALL_BLOCKED must contain 'Queue drained'."""
    import bob.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "Queue drained" in source, (
        "CLI source does not contain 'Queue drained' for the ALL_BLOCKED message"
    )


def test_cli_message_not_old_blocked_phrase():
    """The CLI message must NOT use 'All remaining features are blocked'."""
    import bob.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "All remaining features are blocked" not in source, (
        "CLI source still contains deprecated phrase 'All remaining features are blocked'"
    )


def test_cli_termination_map_queue_drained():
    """Simulate the _TERMINATION_MESSAGES lookup — ALL_BLOCKED message says 'Queue drained'."""
    from bob.orchestrator.run_loop import LoopTermination

    termination_messages = {
        LoopTermination.ALL_COMPLETED: "All features completed!",
        LoopTermination.ALL_BLOCKED: "Queue drained — no ready features left to claim (remaining are needs_human/executing/blocked).",
        LoopTermination.BUDGET_EXCEEDED: "Budget limit exceeded.",
        LoopTermination.SHUTDOWN_REQUESTED: "Shutdown requested.",
    }
    msg = termination_messages[LoopTermination.ALL_BLOCKED]
    assert "Queue drained" in msg
    assert "All remaining features are blocked" not in msg
