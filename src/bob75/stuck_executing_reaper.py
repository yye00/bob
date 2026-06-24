"""bob75 stuck-executing reaper — detect and reset silently-dead subagents.

Provides the bob75-namespace surface for the stuck-executing reaper that scans
features with status='executing' and resets those whose subagent process died
silently.

Satisfies ACs:
  - File exists: src/bob75/stuck_executing_reaper.py
  - Function defined: bob75.stuck_executing_reaper.reap_stuck_executing
  - integration: orchestrator

The heavy logic lives in bob3.orchestrator.stuck_executing_reaper; this module
re-exports the canonical API at the bob75 namespace level and provides
reap_stuck_executing as the primary entry point.

Without this guard a silent claude CLI crash leaves a row stuck at
'executing' indefinitely. The orchestrator never re-dispatches it, the round
stalls without raising NH/halt because the pipeline "looks busy", and only a
manual SQL reset unblocks it. (Observed in bob3 v.13 r10: feature f8bf1630
stuck >50 min after its subagent died.)
"""

from __future__ import annotations

from bob3.orchestrator.stuck_executing_reaper import (  # noqa: F401 — re-exported
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
    """Scan 'executing' features and reset those whose subagent is gone.

    This is the canonical bob75-namespace entry point for the stuck-executing
    reaper. Delegates to bob3.orchestrator.stuck_executing_reaper.sweep_stuck_executing.

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
    "DEFAULT_HEARTBEAT_TIMEOUT_SECONDS",
    "find_stuck_features",
    "reap_stuck_executing",
    "reap_stuck_feature",
    "subagent_alive",
    "sweep_stuck_executing",
]
