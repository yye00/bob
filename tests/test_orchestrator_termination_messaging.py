"""Tests for orchestrator termination messaging — feature 983362dd-2a69-48ad-9b58-20aadbc6f9e5.

Verifies that the ALL_BLOCKED termination label is translated to QUEUE_DRAINED
in log output and that the CLI presents the clearer user-facing message.
"""
from __future__ import annotations

import logging


def _make_orch():
    """Return a minimal OrchestrationLoop instance bypassing __init__."""
    from bob.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


# ---------------------------------------------------------------------------
# format_termination_message
# ---------------------------------------------------------------------------


def test_format_termination_message_all_blocked_returns_queue_drained():
    from bob.orchestrator.run_loop import LoopTermination, format_termination_message

    assert format_termination_message(LoopTermination.ALL_BLOCKED) == "QUEUE_DRAINED"


def test_format_termination_message_all_completed_unchanged():
    from bob.orchestrator.run_loop import LoopTermination, format_termination_message

    assert format_termination_message(LoopTermination.ALL_COMPLETED) == "ALL_COMPLETED"


def test_format_termination_message_budget_exceeded_unchanged():
    from bob.orchestrator.run_loop import LoopTermination, format_termination_message

    assert format_termination_message(LoopTermination.BUDGET_EXCEEDED) == "BUDGET_EXCEEDED"


def test_format_termination_message_none_returns_raised():
    from bob.orchestrator.run_loop import format_termination_message

    assert format_termination_message(None) == "RAISED"


# ---------------------------------------------------------------------------
# translate_termination_label
# ---------------------------------------------------------------------------


def test_translate_termination_label_all_blocked():
    from bob.orchestrator.run_loop import translate_termination_label

    assert translate_termination_label("ALL_BLOCKED") == "QUEUE_DRAINED"


def test_translate_termination_label_passthrough():
    from bob.orchestrator.run_loop import translate_termination_label

    for name in ("ALL_COMPLETED", "BUDGET_EXCEEDED", "SHUTDOWN_REQUESTED"):
        assert translate_termination_label(name) == name


# ---------------------------------------------------------------------------
# Log-line assertions via _emit_run_summary
# ---------------------------------------------------------------------------


def test_log_shows_queue_drained_not_all_blocked(caplog):
    """Run summary must log QUEUE_DRAINED instead of ALL_BLOCKED."""
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "QUEUE_DRAINED" in combined
    assert "termination=ALL_BLOCKED" not in combined


def test_log_run_finished_line_present(caplog):
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    assert any("Run finished:" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# CLI message
# ---------------------------------------------------------------------------


def test_cli_all_blocked_message_contains_queue_drained():
    """The CLI message for ALL_BLOCKED must mention 'Queue drained'."""
    import bob.cli as cli_module
    import inspect

    source = inspect.getsource(cli_module)
    assert "Queue drained" in source


def test_cli_all_blocked_message_mentions_needs_human_and_blocked():
    """The CLI message should clarify the remaining feature states."""
    import bob.cli as cli_module
    import inspect

    source = inspect.getsource(cli_module)
    assert "needs_human" in source
    assert "blocked" in source


# ---------------------------------------------------------------------------
# Enum stability
# ---------------------------------------------------------------------------


def test_all_blocked_enum_value_unchanged():
    """LoopTermination.ALL_BLOCKED.value must stay 'all_blocked' for DB compat."""
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value == "all_blocked"
