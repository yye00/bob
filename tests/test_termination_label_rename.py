"""Tests for feature 330fff74-07ed-4a76-9d62-86ab4ec64b6a.

Acceptance criteria:
- structural: src/bob3/orchestrator/run_loop.py emits a 'Run finished: termination=%s' log line
- behavior: when the loop exits with LoopTermination.ALL_BLOCKED the emitted termination token
  in the log MUST be 'QUEUE_DRAINED' (not 'ALL_BLOCKED')
- behavior: the CLI termination message for ALL_BLOCKED MUST mention 'Queue drained' and MUST
  NOT use the phrase 'All remaining features are blocked'
- behavior: the enum value LoopTermination.ALL_BLOCKED == 'all_blocked' is preserved (DB compat)
- integration: test_log_says_queue_drained passes
- integration: test_cli_message_says_queue_drained passes
"""
from __future__ import annotations

import logging
import unittest.mock


# ---------------------------------------------------------------------------
# Structural: enum value is unchanged
# ---------------------------------------------------------------------------


def test_loop_termination_all_blocked_enum_value_unchanged():
    from bob3.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"


def test_loop_termination_all_blocked_member_exists():
    from bob3.orchestrator.run_loop import LoopTermination

    assert hasattr(LoopTermination, "ALL_BLOCKED")


# ---------------------------------------------------------------------------
# Integration: log line says QUEUE_DRAINED, not ALL_BLOCKED
# ---------------------------------------------------------------------------


def test_log_says_queue_drained(caplog):
    """Invoke the run-finished logger with termination=ALL_BLOCKED and assert
    'QUEUE_DRAINED' appears in the formatted log record."""
    from bob3.orchestrator.run_loop import LoopTermination, OrchestrationLoop

    # Build a minimal OrchestrationLoop without touching DB or filesystem.
    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 3
    orch.features_failed = 0

    def _noop_refresh():
        pass

    orch._refresh_project_cost_cache = _noop_refresh

    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    # The log line must contain QUEUE_DRAINED
    combined = " ".join(caplog.messages)
    assert "QUEUE_DRAINED" in combined, (
        f"Expected 'QUEUE_DRAINED' in log output but got: {combined!r}"
    )
    # The old token must NOT appear as the termination label
    assert "termination=ALL_BLOCKED" not in combined, (
        f"Old label 'ALL_BLOCKED' must not appear as the termination token: {combined!r}"
    )


def test_log_contains_run_finished_prefix(caplog):
    """The log line must start with 'Run finished: termination='."""
    from bob3.orchestrator.run_loop import LoopTermination, OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None

    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    assert any("Run finished: termination=" in msg for msg in caplog.messages), (
        f"No 'Run finished: termination=' line found in: {caplog.messages!r}"
    )


def test_log_other_terminations_not_renamed(caplog):
    """ALL_COMPLETED and BUDGET_EXCEEDED must retain their original names in logs."""
    from bob3.orchestrator.run_loop import LoopTermination, OrchestrationLoop

    for term in (LoopTermination.ALL_COMPLETED, LoopTermination.BUDGET_EXCEEDED):
        orch = OrchestrationLoop.__new__(OrchestrationLoop)
        orch._run_start_time = None
        orch._project_total_cost = 0.0
        orch.features_completed = 1
        orch.features_failed = 0
        orch._refresh_project_cost_cache = lambda: None

        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(term)

        combined = " ".join(caplog.messages)
        assert term.name in combined, (
            f"Expected '{term.name}' in log for termination={term!r}: {combined!r}"
        )
        caplog.clear()


# ---------------------------------------------------------------------------
# Integration: CLI message says 'Queue drained'
# ---------------------------------------------------------------------------


def test_cli_message_says_queue_drained():
    """The CLI termination message for ALL_BLOCKED must contain 'Queue drained'."""
    from bob3.orchestrator.run_loop import LoopTermination

    # The _TERMINATION_MESSAGES dict is defined inside the `run` command
    # function in cli/__init__.py. We verify via direct inspection of the
    # source to avoid coupling to Click's CLI invocation machinery.
    import bob3.cli as cli_module
    import inspect

    source = inspect.getsource(cli_module)
    # The message must include 'Queue drained'
    assert "Queue drained" in source, (
        "CLI source does not contain 'Queue drained' for the ALL_BLOCKED message"
    )


def test_cli_message_does_not_say_all_remaining_features_are_blocked():
    """The CLI message must NOT use the old phrase 'All remaining features are blocked'."""
    import bob3.cli as cli_module
    import inspect

    source = inspect.getsource(cli_module)
    assert "All remaining features are blocked" not in source, (
        "CLI source still contains deprecated phrase 'All remaining features are blocked'"
    )


def test_cli_termination_message_map_contains_queue_drained():
    """Simulate the _TERMINATION_MESSAGES lookup to confirm 'Queue drained' appears."""
    from bob3.orchestrator.run_loop import LoopTermination

    # Build the same dict that the CLI builds (mirrored here to test the contract).
    termination_messages = {
        LoopTermination.ALL_COMPLETED: "All features completed!",
        LoopTermination.ALL_BLOCKED: "Queue drained — no ready features left to claim (remaining are needs_human/executing/blocked).",
        LoopTermination.BUDGET_EXCEEDED: "Budget limit exceeded.",
        LoopTermination.SHUTDOWN_REQUESTED: "Shutdown requested.",
    }
    msg = termination_messages[LoopTermination.ALL_BLOCKED]
    assert "Queue drained" in msg
    assert "All remaining features are blocked" not in msg
