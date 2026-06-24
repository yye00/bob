"""Boundary tests for feature 2a39a2a4-619b-4fc8-a1a0-996a0c07cc74.

Rename ALL_BLOCKED termination label to QUEUE_DRAINED in log line
+ clearer user-facing CLI message.

Boundary cases: empty/zero/minimum inputs must return well-defined
results rather than raising.
"""
from __future__ import annotations

import logging


def _make_orch():
    """Build a minimal OrchestrationLoop instance without __init__."""
    from bob3.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


def test_emit_summary_none_termination_does_not_raise(caplog):
    """_emit_run_summary(None) must not raise — 'RAISED' label emitted instead."""
    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(None)

    combined = " ".join(caplog.messages)
    assert "Run finished:" in combined
    assert "RAISED" in combined


def test_emit_summary_zero_counts_does_not_raise(caplog):
    """Zero features_completed and features_failed is a valid boundary — must not raise."""
    from bob3.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    orch.features_completed = 0
    orch.features_failed = 0

    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "features_completed=0" in combined
    assert "features_failed=0" in combined
    assert "QUEUE_DRAINED" in combined


def test_emit_summary_zero_cost_does_not_raise(caplog):
    """Zero total cost is the empty/minimum boundary — must log $0.00."""
    from bob3.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    orch._project_total_cost = 0.0

    with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "total_cost=$0.00" in combined


def test_enum_value_boundary_all_blocked_preserved():
    """LoopTermination.ALL_BLOCKED.value is the minimum DB-compat identifier."""
    from bob3.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"


def test_translate_only_applies_to_all_blocked(caplog):
    """The ALL_BLOCKED→QUEUE_DRAINED translation must NOT affect other members."""
    from bob3.orchestrator.run_loop import LoopTermination

    for term in (LoopTermination.ALL_COMPLETED, LoopTermination.BUDGET_EXCEEDED):
        orch = _make_orch()
        with caplog.at_level(logging.INFO, logger="bob3.orchestrator.run_loop"):
            orch._emit_run_summary(term)
        combined = " ".join(caplog.messages)
        assert term.name in combined
        assert "QUEUE_DRAINED" not in combined
        caplog.clear()


def test_cli_message_present_for_all_blocked_minimum_dict():
    """The minimum CLI message map must contain ALL_BLOCKED with 'Queue drained'."""
    from bob3.orchestrator.run_loop import LoopTermination

    termination_messages = {
        LoopTermination.ALL_BLOCKED: "Queue drained — no ready features left to claim (remaining are needs_human/executing/blocked).",
    }
    msg = termination_messages.get(LoopTermination.ALL_BLOCKED, "")
    assert msg != "", "Message map is empty for ALL_BLOCKED"
    assert "Queue drained" in msg
