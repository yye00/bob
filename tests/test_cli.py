"""Tests for bob3.cli focusing on the QUEUE_DRAINED rename and CLI message.

Verifies that:
- CLI maps ALL_BLOCKED to the updated "Queue drained" user-facing message
- Old "All remaining features are blocked" phrase is absent from CLI source
- Exit code mapping for ALL_BLOCKED is preserved
"""
from __future__ import annotations

import inspect


def test_cli_module_importable():
    """bob3.cli can be imported."""
    import bob3.cli as cli_module

    assert cli_module is not None


def test_cli_queue_drained_message_present():
    """CLI source must contain 'Queue drained' as the ALL_BLOCKED user message."""
    import bob3.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "Queue drained" in source


def test_cli_old_blocked_phrase_absent():
    """CLI source must NOT contain the old 'All remaining features are blocked' phrase."""
    import bob3.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "All remaining features are blocked" not in source


def test_cli_all_blocked_message_mentions_states():
    """The ALL_BLOCKED CLI message must mention the sub-states it covers."""
    import bob3.cli as cli_module

    source = inspect.getsource(cli_module)
    # The message should clarify what "remaining" means
    assert "needs_human" in source or "executing" in source


def test_cli_loop_termination_all_blocked_exit_code():
    """ALL_BLOCKED must map to a non-zero exit code in the CLI."""
    from bob3.cli import _build_exit_codes  # type: ignore[attr-defined]
    from bob3.orchestrator.run_loop import LoopTermination

    exit_codes = _build_exit_codes()
    code = exit_codes.get(LoopTermination.ALL_BLOCKED)
    assert code is not None
    assert code != 0


def test_cli_termination_message_map_has_all_blocked():
    """The CLI termination message dict must have an entry for ALL_BLOCKED."""
    import bob3.cli as cli_module
    from bob3.orchestrator.run_loop import LoopTermination

    source = inspect.getsource(cli_module)
    # ALL_BLOCKED key should appear in a message map
    assert "ALL_BLOCKED" in source
