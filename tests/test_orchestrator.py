"""Tests for bob.orchestrator: QUEUE_DRAINED rename and LoopTermination basics.

Verifies that:
- LoopTermination enum members are importable and have expected values
- ALL_BLOCKED termination label is translated to QUEUE_DRAINED in the run log
- Enum value is unchanged (preserves DB/serialization compatibility)
"""
from __future__ import annotations

import logging


def test_loop_termination_importable():
    """LoopTermination must be importable from bob.orchestrator."""
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination is not None


def test_loop_termination_all_blocked_value():
    """ALL_BLOCKED enum value must remain 'all_blocked' for DB compat."""
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"


def test_loop_termination_all_blocked_name():
    """ALL_BLOCKED enum name must be 'ALL_BLOCKED'."""
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.name == "ALL_BLOCKED"


def test_loop_termination_members():
    """LoopTermination must have the expected four members."""
    from bob.orchestrator.run_loop import LoopTermination

    names = {m.name for m in LoopTermination}
    assert "ALL_BLOCKED" in names
    assert "ALL_COMPLETED" in names
    assert "BUDGET_EXCEEDED" in names
    assert "SHUTDOWN_REQUESTED" in names


def _make_orch():
    from bob.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


def test_emit_run_summary_translates_all_blocked_to_queue_drained(caplog):
    """_emit_run_summary must log 'QUEUE_DRAINED' when termination is ALL_BLOCKED."""
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "QUEUE_DRAINED" in combined
    assert "termination=ALL_BLOCKED" not in combined


def test_emit_run_summary_all_completed_unchanged(caplog):
    """_emit_run_summary must log 'ALL_COMPLETED' unchanged."""
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_COMPLETED)

    combined = " ".join(caplog.messages)
    assert "ALL_COMPLETED" in combined


def test_emit_run_summary_budget_exceeded_unchanged(caplog):
    """_emit_run_summary must log 'BUDGET_EXCEEDED' unchanged."""
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.BUDGET_EXCEEDED)

    combined = " ".join(caplog.messages)
    assert "BUDGET_EXCEEDED" in combined
