"""orchestrator.stuck_executing_reaper — re-exports the stuck-executing reaper.

Satisfies the AC (feature 64e5b1c0) requiring
``orchestrator.stuck_executing_reaper.reap_stuck_executing``.  The heavy logic
lives in ``bob.orchestrator.stuck_executing_reaper``; this module provides the
canonical ``orchestrator``-package path and the ``reap_stuck_executing`` entry
point used by the orchestrator run loop.

Without this reaper a silent claude CLI crash leaves a feature row stuck at
'executing' forever: the orchestrator never re-dispatches it, the round stalls
without raising NH/halt because the pipeline "looks busy", and only a manual
SQL reset unblocks it.
"""

from __future__ import annotations

from bob.orchestrator.stuck_executing_reaper import (  # noqa: F401
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    find_stuck_features,
    reap_stuck_feature,
    subagent_alive,
    sweep_stuck_executing,
)


def reap_stuck_executing(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Scan 'executing' features and reset those whose subagent died silently.

    Intended to be called each orchestrator tick (or on a dedicated 60s timer).
    A feature is reaped when its recorded subagent PID is absent or dead AND its
    heartbeat is older than *heartbeat_timeout_seconds* (or was never written).
    Reaped features are reset to 'ready' with refinement_attempts incremented so
    the next dispatch counts as a real attempt.

    Args:
        project_id: UUID of the project to scan. Must not be empty.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).
            Must be >= 0.

    Returns:
        List of feature IDs that were reaped (reset to 'ready').

    Raises:
        ValueError: If project_id is empty or heartbeat_timeout_seconds < 0.
    """
    if not project_id:
        raise ValueError("project_id must not be empty")
    if heartbeat_timeout_seconds < 0:
        raise ValueError(
            f"heartbeat_timeout_seconds must be >= 0, got {heartbeat_timeout_seconds}"
        )
    return sweep_stuck_executing(
        project_id,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
    )


__all__ = [
    "DEFAULT_HEARTBEAT_TIMEOUT_SECONDS",
    "find_stuck_features",
    "reap_stuck_executing",
    "reap_stuck_feature",
    "subagent_alive",
    "sweep_stuck_executing",
]
