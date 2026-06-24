"""Top-level stuck-executing reaper for bob (feature 07770ff2).

Exposes detect_and_reset_stuck_features as the canonical public entry point
required by the acceptance criteria:
  - File exists: src/bob/stuck_executing_reaper.py
  - Function defined: bob.stuck_executing_reaper.detect_and_reset_stuck_features
  - Function defined: bob.stuck_executing_reaper.reap_stuck_executing
  - Function defined: bob.stuck_executing_reaper.record_reap
  - integration: bob.orchestrator

The heavy logic lives in bob.orchestrator.stuck_executing_reaper; this module
provides the expected top-level path and function name.

Without this guard a silent claude CLI crash leaves a row stuck at
'executing' indefinitely.  The orchestrator never re-dispatches it, the round
stalls without raising NH/halt because the pipeline "looks busy", and only a
manual SQL reset unblocks it.  (Observed in bob v.13 r10: feature f8bf1630
stuck >50 min after its subagent died.)

Public API
----------
detect_and_reset_stuck_features(project_id, heartbeat_timeout_seconds)
    Scan 'executing' features, reset stuck ones to 'ready', return reaped IDs.

record_reap(feature_id, reap_count, now)
    Stamp last_reap_at and reap_count onto a feature row after a reap event.
    Delegates to bob.reaper.stamp_reap_metadata.
"""

from __future__ import annotations

from datetime import datetime

from bob.orchestrator.stuck_executing_reaper import (
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    find_stuck_features,
    reap_stuck_feature,
    subagent_alive,
    sweep_stuck_executing,
)
from bob.reaper import (  # noqa: F401 — AC aliases
    detect_stuck_executing,
    reset_stuck_feature as _reset_stuck_feature_impl,
)

# AC alias: "Function defined: bob.stuck_executing_reaper.is_subagent_alive"
is_subagent_alive = subagent_alive

# AC alias: "Function defined: bob.stuck_executing_reaper.reset_stuck_feature"
reset_stuck_feature = _reset_stuck_feature_impl

# AC alias: "Function defined: bob.stuck_executing_reaper.detect_stuck_features"
# Required by feature 71d80a96 — returns list of stuck feature objects (not IDs)
detect_stuck_features = find_stuck_features


def detect_and_reset_stuck_features(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Scan 'executing' features and reset those whose subagent is gone.

    Every orchestrator tick (or a dedicated 60s timer) should call this.
    Idempotent: resetting an already-reset feature is harmless.

    A feature is considered stuck when its recorded subagent PID is absent or
    dead AND its heartbeat timestamp is older than heartbeat_timeout_seconds (or
    was never written).  The feature is then reset to 'ready' and
    refinement_attempts is incremented so the next dispatch counts as a real
    attempt.  The reap event is logged with the prior PID and heartbeat age.

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


def reap_stuck_executing(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Scan 'executing' features and reset those whose subagent is gone.

    Canonical entry point required by feature 10273c3c acceptance criteria.
    Delegates to sweep_stuck_executing (same behaviour as
    detect_and_reset_stuck_features).

    Every orchestrator tick (or a dedicated 60s timer) should call this.
    Idempotent: resetting an already-reset feature is harmless.

    A feature is considered stuck when its recorded subagent PID is absent or
    dead AND its heartbeat timestamp is older than heartbeat_timeout_seconds (or
    was never written).  The feature is then reset to 'ready' and
    refinement_attempts is incremented so the next dispatch counts as a real
    attempt.  The reap event is logged with the prior PID and heartbeat age.

    Args:
        project_id: UUID of the project to scan.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).

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


def record_reap(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Stamp last_reap_at and reap_count onto a feature row after a reap event.

    Called by the stuck_executing_reaper after resetting a feature to 'ready'.
    These two fields are the persistent memory used by the dispatch loop to
    enforce exponential backoff (df830312).

    Raises ValueError if feature_id is empty or reap_count is negative.

    Args:
        feature_id: UUID of the feature that was reaped.
        reap_count: New (post-reap) reap_count to write. Must be >= 0.
        now: Timestamp to use as last_reap_at (defaults to UTC now).

    Raises:
        ValueError: If feature_id is empty or reap_count < 0.
    """
    if not feature_id:
        raise ValueError("feature_id must not be empty")
    if reap_count < 0:
        raise ValueError(f"reap_count must be >= 0, got {reap_count}")

    from bob.reaper import stamp_reap_metadata  # noqa: PLC0415

    stamp_reap_metadata(feature_id, reap_count, now=now)


def stamp_reap_metadata(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Stamp last_reap_at and reap_count onto a feature row after a reap event.

    AC alias required by feature 620de3da:
    "Function defined: bob.stuck_executing_reaper.stamp_reap_metadata"

    Delegates to bob.reaper.stamp_reap_metadata for the DB write.

    Args:
        feature_id: UUID of the feature that was reaped. Must not be empty.
        reap_count: New (post-reap) reap_count to write. Must be >= 0.
        now: Timestamp to use as last_reap_at (defaults to UTC now).

    Raises:
        ValueError: If feature_id is empty or reap_count is negative.
    """
    if not feature_id:
        raise ValueError("feature_id must not be empty")
    if not isinstance(reap_count, int):
        raise ValueError(
            f"reap_count must be an int, got {type(reap_count).__name__}"
        )
    if reap_count < 0:
        raise ValueError(f"reap_count must be >= 0, got {reap_count}")

    from bob.reaper import stamp_reap_metadata as _stamp  # noqa: PLC0415

    _stamp(feature_id, reap_count=reap_count, now=now)


# AC alias: "Function defined: bob.stuck_executing_reaper.detect_and_reap_stuck_features"
detect_and_reap_stuck_features = detect_and_reset_stuck_features

# AC alias: "Function defined: bob.stuck_executing_reaper.reap_stuck_executing_features"
# Required by feature 6a879022-4dc2-48ef-9b3d-b0dc016b5aaa
reap_stuck_executing_features = reap_stuck_executing

# AC alias: "Function defined: bob.stuck_executing_reaper.reset_feature_status"
# Required by feature f682e8d7-36e1-4624-8fc1-ffbe83e9ea39
reset_feature_status = reset_stuck_feature

# AC alias: "Function defined: bob.stuck_executing_reaper.reset_executing_feature"
# Required by feature e260b7dc-d3dd-4c4a-acd1-ed39ba7091d7
reset_executing_feature = reset_stuck_feature

__all__ = [
    "DEFAULT_HEARTBEAT_TIMEOUT_SECONDS",
    "detect_and_reap_stuck_features",
    "detect_and_reset_stuck_features",
    "detect_stuck_executing",
    "detect_stuck_features",
    "find_stuck_features",
    "is_subagent_alive",
    "reap_stuck_executing",
    "reap_stuck_executing_features",
    "reap_stuck_feature",
    "record_reap",
    "reset_executing_feature",
    "reset_feature_status",
    "reset_stuck_feature",
    "stamp_reap_metadata",
    "subagent_alive",
    "sweep_stuck_executing",
]
