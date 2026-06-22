"""Stuck-executing reaper — detect and reset features whose subagent died silently.

Every orchestrator tick (or on a dedicated 60s timer), scan features with
status='executing' and verify their subagent process is alive (via recorded
subagent_pid or heartbeat timestamp). If the subagent process is missing AND
no heartbeat within the last N seconds (default 300), reset status to 'ready'
and increment refinement_attempts so the next dispatch counts as a real attempt.

Observed in bob3 v.13 r10: feature f8bf1630 stuck >50min after its subagent
died — no live process, only a manual SQL reset unblocked it.

Public API
----------
stuck_executing_reaper_detect_reset_features_whose_subagent(project_id, heartbeat_timeout_seconds)
    Scan 'executing' features and reset those whose subagent is gone.
    Returns a list of reaped feature IDs.
"""

from __future__ import annotations

from bob3.orchestrator.stuck_executing_reaper import (
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    find_stuck_features,
    reap_stuck_feature,
    subagent_alive,
    sweep_stuck_executing,
)


def stuck_executing_reaper_detect_reset_features_whose_subagent(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Scan 'executing' features and reset those whose subagent is gone.

    Every orchestrator tick (or a dedicated 60s timer) should call this.
    Idempotent: resetting an already-reset feature is harmless.

    A feature is considered stuck when its recorded subagent PID is absent or
    dead AND its heartbeat timestamp is older than heartbeat_timeout_seconds (or
    was never written). The feature is then reset to 'ready' and
    refinement_attempts is incremented so the next dispatch counts as a real
    attempt. The reap event is logged with the prior PID and heartbeat age.

    Args:
        project_id: UUID of the project to scan.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).

    Returns:
        List of feature IDs that were reaped (reset to 'ready').
    """
    return sweep_stuck_executing(
        project_id,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
    )


__all__ = [
    "stuck_executing_reaper_detect_reset_features_whose_subagent",
    "find_stuck_features",
    "reap_stuck_feature",
    "subagent_alive",
    "sweep_stuck_executing",
    "DEFAULT_HEARTBEAT_TIMEOUT_SECONDS",
]
