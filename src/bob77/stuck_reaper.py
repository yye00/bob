"""bob77.stuck_reaper — Stuck-executing reaper for the bob77 orchestrator.

Delegates to bob3.stuck_reaper.detect_and_reset_stuck_features, which scans
features with status='executing' and verifies their subagent process is alive.
If the subagent process is missing AND no heartbeat within heartbeat_timeout_seconds
(default 300), the feature is reset to 'ready' and refinement_attempts is
incremented so the next dispatch counts as a real attempt.

Without this guard a silent claude CLI crash leaves a row stuck at 'executing'
indefinitely.  The orchestrator never re-dispatches it, the round stalls without
raising NH/halt because the pipeline "looks busy", and only a manual SQL reset
unblocks it.  (Observed in bob3 v.13 r10: feature f8bf1630 stuck >50 min.)

Public API
----------
detect_and_reset_stuck_features(project_id, heartbeat_timeout_seconds)
    Scan 'executing' features, reset stuck ones to 'ready', return reaped IDs.
"""

from __future__ import annotations

from bob3.stuck_reaper import (  # noqa: F401 — integration: bob77.orchestrator
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    detect_and_reset_stuck_features,
)

__all__ = ["detect_and_reset_stuck_features", "DEFAULT_HEARTBEAT_TIMEOUT_SECONDS"]
