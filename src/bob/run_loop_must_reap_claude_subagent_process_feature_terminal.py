"""run_loop_must_reap_claude_subagent_process_feature_terminal — reap claude subagent on feature terminal-state transition.

Closes the orphan subagent resource leak observed in bob version 14 round 11:
a claude subagent launched for feature 5cba1ba1 persisted for 57 minutes after
the feature transitioned to 'completed', holding an open sonnet-4.6 API
connection, a stream-json parser, an MCP plugin loader, and ~50 zombie helper
processes.

This facade exposes the canonical reap entry point used by the run_loop
completion handler so that other modules can import from the top-level bob
namespace without depending on the internal orchestrator layout.

Applies to all terminal transitions: completed, needs_human, regression, failed.

Public API
----------
run_loop_must_reap_claude_subagent_process_feature_terminal(feature_id, status=None) -> list[int]
    Reap claude subagent(s) tagged with feature_id.  Sends SIGTERM then
    SIGKILL (15s grace window) and emits audit sentinel
    subagent_reaped_on_terminal=<feature_id>.  Returns list of reaped PIDs.
    Exceptions from the underlying reaper are caught; empty list is returned.

sweep_orphan_subagents() -> list[tuple[str, int]]
    Backstop sweep: reap subagents whose tagged feature is in a terminal state
    for >5 minutes.  Catches handler-bypass paths (e.g. SIGKILL'd orchestrator
    restart mid-completion).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "run_loop_must_reap_claude_subagent_process_feature_terminal",
    "sweep_orphan_subagents",
    "reap_subagent_for_feature",
]

# Terminal states that require subagent reaping.
_TERMINAL_STATUSES = frozenset({"completed", "needs_human", "regression", "failed"})


def reap_subagent_for_feature(feature_id: str) -> list[int]:
    """Re-export of bob.orchestrator.subagent_reaper.reap_subagent_for_feature.

    Lazy import avoids circular dependency (bob.orchestrator.__init__ →
    run_loop → this module → bob.orchestrator.subagent_reaper).
    """
    from bob.orchestrator.subagent_reaper import (
        reap_subagent_for_feature as _reap,
    )
    return _reap(feature_id)


def _sweep_orphans() -> list[tuple[str, int]]:
    """Lazy wrapper around bob.orchestrator.subagent_reaper.sweep_orphan_subagents."""
    from bob.orchestrator.subagent_reaper import sweep_orphan_subagents as _sweep
    return _sweep()


def run_loop_must_reap_claude_subagent_process_feature_terminal(
    feature_id: str,
    status: str | None = None,
) -> list[int]:
    """Reap claude subagent process when a feature reaches a terminal state.

    Called by the run_loop completion handler immediately after a feature
    transitions to completed, needs_human, regression, or failed.  Delegates
    to bob.orchestrator.subagent_reaper.reap_subagent_for_feature which:

    1. Scans /proc for claude processes tagged with feature_id.
    2. Sends SIGTERM.
    3. Waits up to 15 seconds for clean exit.
    4. Sends SIGKILL if still alive.
    5. Emits audit sentinel ``subagent_reaped_on_terminal=<feature_id>`` on
       confirmed death.

    Errors from the reaper are caught and logged; an empty list is returned
    so the caller's completion path is never interrupted.

    Args:
        feature_id: UUID of the feature that has entered a terminal state.
        status: The terminal status (completed, needs_human, regression, failed).
            Accepted for logging; reaping applies to all terminal transitions.

    Returns:
        List of integer PIDs confirmed dead.  Empty when no matching subagent
        was found or when the reaper encountered an error.
    """
    try:
        reaped = reap_subagent_for_feature(feature_id)
        if reaped:
            logger.info(
                "run_loop_must_reap: reaped %d subagent(s) %s for terminal feature %s (status=%s)",
                len(reaped),
                reaped,
                feature_id[:8],
                status,
            )
        return reaped
    except Exception:
        logger.debug(
            "run_loop_must_reap: reap failed for feature %s; orphan sweeper will catch it",
            feature_id[:8],
            exc_info=True,
        )
        return []


def sweep_orphan_subagents() -> list[tuple[str, int]]:
    """Backstop sweep: reap subagents for features in terminal states >5min.

    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart
    mid-completion) where the completion handler never ran.  Idempotent
    and safe to run concurrently with other reapers.

    Returns:
        List of (feature_id, pid) pairs that were reaped.
    """
    return _sweep_orphans()
