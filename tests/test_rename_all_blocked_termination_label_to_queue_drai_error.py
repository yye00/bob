"""Error-path tests for feature 2a39a2a4-619b-4fc8-a1a0-996a0c07cc74.

Rename ALL_BLOCKED termination label to QUEUE_DRAINED in log line
+ clearer user-facing CLI message.

Error cases: invalid input raises ValueError and functions do not
silently succeed.
"""
from __future__ import annotations

import logging

import pytest


def _make_orch():
    """Build a minimal OrchestrationLoop instance without __init__."""
    from bob.orchestrator.run_loop import OrchestrationLoop

    orch = OrchestrationLoop.__new__(OrchestrationLoop)
    orch._run_start_time = None
    orch._project_total_cost = 0.0
    orch.features_completed = 0
    orch.features_failed = 0
    orch._refresh_project_cost_cache = lambda: None
    return orch


def test_loop_termination_all_blocked_invalid_string_raises():
    """LoopTermination('BAD_VALUE') must raise ValueError — not silently succeed."""
    from bob.orchestrator.run_loop import LoopTermination

    with pytest.raises(ValueError):
        LoopTermination("not_a_valid_termination")


def test_loop_termination_empty_string_raises():
    """LoopTermination('') must raise ValueError — empty string is invalid."""
    from bob.orchestrator.run_loop import LoopTermination

    with pytest.raises(ValueError):
        LoopTermination("")


def test_log_does_not_contain_all_blocked_as_termination_token(caplog):
    """After rename, 'termination=ALL_BLOCKED' must never appear in log output."""
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    for msg in caplog.messages:
        assert "termination=ALL_BLOCKED" not in msg, (
            f"Deprecated token 'termination=ALL_BLOCKED' found in log: {msg!r}"
        )


def test_queue_drained_token_present_when_all_blocked(caplog):
    """'QUEUE_DRAINED' must be present in the log when ALL_BLOCKED terminates a run."""
    from bob.orchestrator.run_loop import LoopTermination

    orch = _make_orch()
    with caplog.at_level(logging.INFO, logger="bob.orchestrator.run_loop"):
        orch._emit_run_summary(LoopTermination.ALL_BLOCKED)

    combined = " ".join(caplog.messages)
    assert "QUEUE_DRAINED" in combined, (
        f"'QUEUE_DRAINED' missing from log output: {combined!r}"
    )


def test_cli_message_does_not_silently_use_old_phrase():
    """The CLI source must not silently still carry 'All remaining features are blocked'."""
    import inspect

    import bob.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "All remaining features are blocked" not in source, (
        "CLI source still silently carries deprecated phrase"
    )


def test_enum_value_not_renamed():
    """LoopTermination.ALL_BLOCKED.value must NOT be 'queue_drained' — renaming would break DB."""
    from bob.orchestrator.run_loop import LoopTermination

    assert LoopTermination.ALL_BLOCKED.value != "queue_drained", (
        "Enum VALUE was incorrectly renamed; only the user-visible label should change"
    )
