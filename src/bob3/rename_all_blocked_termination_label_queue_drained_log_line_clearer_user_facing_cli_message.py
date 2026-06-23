"""Rename ALL_BLOCKED termination label to QUEUE_DRAINED in log output and CLI.

``LoopTermination.ALL_BLOCKED`` reads as a stuck/failure state but actually
signals a clean exit: the ready queue is empty and the orchestrator has nothing
eligible to claim.  This module provides a translation function used in:

- ``run_loop.py`` — the "Run finished: termination=..." log line
- ``cli/__init__.py`` — the user-facing Rich console message

The enum value ``all_blocked`` is intentionally preserved for DB/serialization
compatibility; only the user-visible string differs.
"""
from __future__ import annotations


def rename_all_blocked_termination_label_queue_drained_log_line_clearer_user_facing_cli_message(
    termination_name: str,
) -> str:
    """Translate the ``ALL_BLOCKED`` termination label to ``QUEUE_DRAINED``.

    Only the exact string ``"ALL_BLOCKED"`` (the ``LoopTermination.ALL_BLOCKED.name``
    form) is translated.  All other strings — including the raw enum value
    ``"all_blocked"`` — are returned unchanged.
    """
    if termination_name == "ALL_BLOCKED":
        return "QUEUE_DRAINED"
    return termination_name


def cli_message_for_all_blocked() -> str:
    """Return the user-facing CLI message for the ALL_BLOCKED / QUEUE_DRAINED outcome."""
    return (
        "Queue drained — no ready features left to claim "
        "(remaining are needs_human/executing/blocked)."
    )
