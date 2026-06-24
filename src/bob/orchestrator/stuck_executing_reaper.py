"""Stuck-executing reaper — detect and reset silently-dead subagents (b596a38a).

Every orchestrator tick (or on a dedicated 60s timer) this module scans
features with status='executing' and verifies that their recorded subagent
process is still alive.  If the process is missing AND the feature's
heartbeat is stale (or was never written), the feature is reset to 'ready'
and refinement_attempts is incremented so the next dispatch counts as a real
attempt.

The reap event is logged with the prior PID and last-heartbeat age so
operators can diagnose patterns without manual SQL queries.

Without this guard a silent claude CLI crash leaves a row stuck at
'executing' indefinitely.  The orchestrator never re-dispatches it, the round
stalls without raising NH/halt because the pipeline "looks busy", and only a
manual SQL reset unblocks it.  (Observed in bob v.13 r10: feature f8bf1630
stuck >50 min after its subagent died.)

Public API
----------
subagent_alive(pid)
    True iff the OS process with that PID currently exists.

find_stuck_features(project_id, heartbeat_timeout_seconds)
    Return Feature rows that are 'executing' but whose subagent is gone.

reap_stuck_feature(feature, now)
    Reset a single stuck feature to 'ready', bump refinement_attempts, stamp
    last_reap_at / reap_count, and emit a structured log line.

sweep_stuck_executing(project_id, heartbeat_timeout_seconds)
    Convenience wrapper: find then reap all stuck features in one call.
    Intended to be called each orchestrator tick.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob import db

if TYPE_CHECKING:
    from bob.models import Feature

logger = logging.getLogger(__name__)

# Default heartbeat timeout: if the subagent hasn't updated heartbeat within
# this many seconds, treat it as dead (even if the PID still exists — the
# PID may have been reused by an unrelated process).
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def subagent_alive(pid: int) -> bool:
    """Return True iff the OS process *pid* currently exists.

    Uses signal 0 (existence probe — no actual signal is delivered).
    Returns False for any PID ≤ 0 (invalid / kernel sentinel).

    Args:
        pid: OS process ID to check.

    Returns:
        True if the process exists, False otherwise.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack permission to signal it — count as alive.
        return True


def _heartbeat_age_seconds(feature: "Feature", now: datetime) -> float | None:
    """Return seconds since feature.subagent_heartbeat_at, or None if not set."""
    hb = getattr(feature, "subagent_heartbeat_at", None)
    if hb is None:
        return None
    if isinstance(hb, str):
        hb = datetime.fromisoformat(hb)
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now - hb).total_seconds())


def _feature_is_stuck(
    feature: "Feature",
    now: datetime,
    heartbeat_timeout_seconds: int,
) -> bool:
    """Return True iff the feature should be reaped.

    A feature is stuck when BOTH:
      1. Its subagent PID is missing (None or dead process).
      2. Its heartbeat is stale (None, or older than heartbeat_timeout_seconds).

    If the PID is alive we never reap — the feature is legitimately executing.
    """
    pid = getattr(feature, "subagent_pid", None)
    pid_alive = pid is not None and subagent_alive(pid)

    if pid_alive:
        return False

    # PID is missing or dead — check heartbeat staleness.
    age = _heartbeat_age_seconds(feature, now)
    if age is None:
        # No heartbeat ever written AND pid is missing/dead → stuck.
        return True
    return age >= heartbeat_timeout_seconds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_stuck_features(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list["Feature"]:
    """Scan 'executing' features and return those whose subagent is gone.

    A feature is considered stuck when its recorded subagent PID is absent
    or dead AND its heartbeat timestamp is older than *heartbeat_timeout_seconds*
    (or was never written).

    Args:
        project_id: UUID of the project to scan.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).

    Returns:
        List of Feature objects that should be reaped.
    """
    now = datetime.now(timezone.utc)
    executing = db.list_features(project_id=project_id, status="executing")
    return [
        f for f in executing
        if _feature_is_stuck(f, now, heartbeat_timeout_seconds)
    ]


def reap_stuck_feature(
    feature: "Feature",
    now: datetime | None = None,
) -> None:
    """Reset a single stuck feature from 'executing' to 'ready'.

    Side effects:
    - Sets status='ready'.
    - Increments refinement_attempts.
    - Stamps last_reap_at = now and increments reap_count.
    - Clears subagent_pid and subagent_heartbeat_at.
    - Emits a structured INFO log with pid, heartbeat age, and new reap_count.

    Args:
        feature: The Feature model instance to reap.
        now: Reference timestamp (defaults to UTC now).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    pid = getattr(feature, "subagent_pid", None)
    age = _heartbeat_age_seconds(feature, now)
    reap_count = (getattr(feature, "reap_count", None) or 0) + 1
    refinement_attempts = (getattr(feature, "refinement_attempts", None) or 0) + 1

    logger.info(
        "STUCK_REAPER: reaping feature %s (%s) — pid=%s heartbeat_age=%.0fs "
        "new_reap_count=%d",
        feature.id[:8],
        feature.name,
        pid,
        age if age is not None else -1,
        reap_count,
    )

    db.update_feature(
        feature.id,
        status="ready",
        refinement_attempts=refinement_attempts,
        last_reap_at=now.isoformat(),
        reap_count=reap_count,
        subagent_pid=None,
        subagent_heartbeat_at=None,
    )


def sweep_stuck_executing(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Find and reap all stuck 'executing' features for *project_id*.

    Intended to be called on each orchestrator tick (or a dedicated timer).
    Idempotent and safe to call concurrently — each reap is an atomic
    UPDATE and double-reaping an already-reset feature is harmless.

    Args:
        project_id: UUID of the project to scan.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).

    Returns:
        List of feature IDs that were reaped.
    """
    stuck = find_stuck_features(
        project_id, heartbeat_timeout_seconds=heartbeat_timeout_seconds
    )
    if not stuck:
        return []

    now = datetime.now(timezone.utc)
    reaped_ids: list[str] = []
    for feature in stuck:
        try:
            reap_stuck_feature(feature, now=now)
            reaped_ids.append(feature.id)
        except Exception:
            logger.warning(
                "STUCK_REAPER: failed to reap feature %s; skipping",
                feature.id[:8],
                exc_info=True,
            )

    return reaped_ids
