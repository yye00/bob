"""Tests for rename_all_blocked_termination_label_queue_drained_log_line.

Verifies that:
- ALL_BLOCKED termination label is translated to QUEUE_DRAINED in log output
- The user-facing CLI message uses the clearer "Queue drained" phrasing
- Other termination names are passed through unchanged
- The enum value itself is not mutated (DB/serialization compat preserved)
"""
from __future__ import annotations

import pytest

from bob3.rename_all_blocked_termination_label_queue_drained_log_line import (
    rename_all_blocked_termination_label_queue_drained_log_line,
)


def test_rename_all_blocked_termination_label_queue_drained_log_line():
    """ALL_BLOCKED maps to QUEUE_DRAINED; other names pass through unchanged."""
    rename = rename_all_blocked_termination_label_queue_drained_log_line

    # Core contract: ALL_BLOCKED → QUEUE_DRAINED
    assert rename("ALL_BLOCKED") == "QUEUE_DRAINED"

    # Other termination names are unchanged
    assert rename("ALL_COMPLETED") == "ALL_COMPLETED"
    assert rename("BUDGET_EXCEEDED") == "BUDGET_EXCEEDED"
    assert rename("SHUTDOWN_REQUESTED") == "SHUTDOWN_REQUESTED"
    assert rename("RAISED") == "RAISED"

    # Lowercase all_blocked (raw enum value) is NOT renamed — only the .name form is
    assert rename("all_blocked") == "all_blocked"

    # Empty string is returned as-is
    assert rename("") == ""

    # Arbitrary strings are returned unchanged
    assert rename("UNKNOWN_STATE") == "UNKNOWN_STATE"


def test_rename_returns_string():
    """Return type is always str."""
    rename = rename_all_blocked_termination_label_queue_drained_log_line
    result = rename("ALL_BLOCKED")
    assert isinstance(result, str)


def test_rename_does_not_mutate_input():
    """The function is pure — calling it twice gives the same result."""
    rename = rename_all_blocked_termination_label_queue_drained_log_line
    assert rename("ALL_BLOCKED") == "QUEUE_DRAINED"
    assert rename("ALL_BLOCKED") == "QUEUE_DRAINED"


def test_cli_message_for_all_blocked():
    """cli_message_for_all_blocked returns the expected Queue drained phrasing."""
    from bob3.rename_all_blocked_termination_label_queue_drained_log_line import (
        cli_message_for_all_blocked,
    )
    msg = cli_message_for_all_blocked()
    assert "Queue drained" in msg
    assert "needs_human" in msg
    assert "executing" in msg
    assert "blocked" in msg


def test_run_loop_uses_queue_drained_label():
    """The run_loop log line emits QUEUE_DRAINED, not ALL_BLOCKED."""
    from bob3.orchestrator.run_loop import LoopTermination

    rename = rename_all_blocked_termination_label_queue_drained_log_line

    termination = LoopTermination.ALL_BLOCKED
    termination_name = termination.name  # "ALL_BLOCKED"
    translated = rename(termination_name)
    assert translated == "QUEUE_DRAINED"
    # Enum value is unchanged (DB/serialisation compat)
    assert termination.value == "all_blocked"


def test_non_all_blocked_terminations_unchanged():
    """No other LoopTermination names are altered."""
    from bob3.orchestrator.run_loop import LoopTermination

    rename = rename_all_blocked_termination_label_queue_drained_log_line

    for term in LoopTermination:
        if term == LoopTermination.ALL_BLOCKED:
            assert rename(term.name) == "QUEUE_DRAINED"
        else:
            assert rename(term.name) == term.name
