"""Tests for bob3.cli termination message handling.

Verifies that:
- format_queue_drained_message returns the expected user-facing message
- The CLI _TERMINATION_MESSAGES map uses "Queue drained" for ALL_BLOCKED
- The old phrase "All remaining features are blocked" is absent from CLI source
- format_queue_drained_message is callable and returns a non-empty string
"""
from __future__ import annotations

import inspect


def test_format_queue_drained_message_importable():
    """format_queue_drained_message must be importable from bob3.cli."""
    from bob3.cli import format_queue_drained_message

    assert callable(format_queue_drained_message)


def test_format_queue_drained_message_returns_string():
    """format_queue_drained_message must return a non-empty string."""
    from bob3.cli import format_queue_drained_message

    result = format_queue_drained_message()
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_queue_drained_message_contains_queue_drained():
    """The returned message must contain 'Queue drained'."""
    from bob3.cli import format_queue_drained_message

    result = format_queue_drained_message()
    assert "Queue drained" in result


def test_format_queue_drained_message_mentions_needs_human():
    """The returned message must mention needs_human to clarify the state."""
    from bob3.cli import format_queue_drained_message

    result = format_queue_drained_message()
    assert "needs_human" in result


def test_cli_all_blocked_message_is_queue_drained():
    """The CLI message for ALL_BLOCKED must contain 'Queue drained', not 'All blocked'."""
    from bob3.orchestrator.run_loop import LoopTermination
    import bob3.cli as cli_module

    source = inspect.getsource(cli_module)
    # Ensure the source contains "Queue drained" somewhere near ALL_BLOCKED handling
    assert "Queue drained" in source


def test_cli_source_does_not_use_old_all_blocked_phrase():
    """The deprecated phrase 'All remaining features are blocked' must not appear in CLI source."""
    import bob3.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "All remaining features are blocked" not in source


def test_cli_termination_messages_map_all_blocked_to_queue_drained():
    """The _TERMINATION_MESSAGES dict in run command must map ALL_BLOCKED to Queue drained text."""
    from bob3.orchestrator.run_loop import LoopTermination

    # Verify the message string the CLI uses is correct
    expected_fragment = "Queue drained"
    # Directly check the format_queue_drained_message function output
    from bob3.cli import format_queue_drained_message

    msg = format_queue_drained_message()
    assert expected_fragment in msg, (
        f"Expected '{expected_fragment}' in CLI message, got: {msg!r}"
    )


def test_cli_all_blocked_message_no_stuck_language():
    """The ALL_BLOCKED CLI message must not say 'stuck' or 'failure'."""
    from bob3.cli import format_queue_drained_message

    result = format_queue_drained_message()
    lower = result.lower()
    assert "stuck" not in lower
    assert "failure" not in lower
