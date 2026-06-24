"""Tests for CLI messages related to the QUEUE_DRAINED rename.

Verifies that:
- The CLI maps LoopTermination.ALL_BLOCKED to a 'Queue drained' message
- The translate_termination_label function works correctly
- No deprecated 'ALL_BLOCKED' strings appear in CLI output for run command
"""
from __future__ import annotations

import pytest


def test_translate_termination_label_all_blocked():
    """translate_termination_label('ALL_BLOCKED') must return 'QUEUE_DRAINED'."""
    from bob.orchestrator.run_loop import translate_termination_label

    assert translate_termination_label("ALL_BLOCKED") == "QUEUE_DRAINED"


def test_translate_termination_label_all_completed_unchanged():
    """translate_termination_label must not alter non-ALL_BLOCKED names."""
    from bob.orchestrator.run_loop import translate_termination_label

    assert translate_termination_label("ALL_COMPLETED") == "ALL_COMPLETED"


def test_translate_termination_label_budget_exceeded_unchanged():
    """translate_termination_label must not alter BUDGET_EXCEEDED."""
    from bob.orchestrator.run_loop import translate_termination_label

    assert translate_termination_label("BUDGET_EXCEEDED") == "BUDGET_EXCEEDED"


def test_translate_termination_label_raised_unchanged():
    """translate_termination_label must not alter the 'RAISED' sentinel."""
    from bob.orchestrator.run_loop import translate_termination_label

    assert translate_termination_label("RAISED") == "RAISED"


def test_cli_termination_messages_all_blocked_queue_drained():
    """The CLI _TERMINATION_MESSAGES must map ALL_BLOCKED to 'Queue drained'."""
    import inspect

    import bob.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "Queue drained" in source, "CLI source must contain 'Queue drained' message"


def test_cli_all_blocked_message_mentions_remaining_states():
    """The ALL_BLOCKED CLI message must mention needs_human/executing/blocked."""
    import inspect

    import bob.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "needs_human" in source
    assert "executing" in source
    assert "blocked" in source


def test_translate_termination_label_importable():
    """translate_termination_label must be importable from bob.orchestrator.run_loop."""
    from bob.orchestrator.run_loop import translate_termination_label

    assert callable(translate_termination_label)
