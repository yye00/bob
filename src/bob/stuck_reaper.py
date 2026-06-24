"""Top-level stuck-executing reaper for bob.

Exposes detect_and_reset_stuck_features as the canonical public entry point.
The heavy lifting lives in bob.orchestrator.stuck_executing_reaper; this
module provides the expected top-level path and function name required by
the feature's acceptance criteria.

Without this guard a silent claude CLI crash leaves a row stuck at
'executing' indefinitely.  The orchestrator never re-dispatches it, the round
stalls without raising NH/halt because the pipeline "looks busy", and only a
manual SQL reset unblocks it.  (Observed in bob v.13 r10: feature f8bf1630
stuck >50 min after its subagent died.)

Public API
----------
detect_and_reset_stuck_features(project_id, heartbeat_timeout_seconds)
    Scan 'executing' features, reset stuck ones to 'ready', return reaped IDs.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob import db
from bob.orchestrator.stuck_executing_reaper import (
    find_stuck_features,
    reap_stuck_feature,
)

if TYPE_CHECKING:
    from bob.models import Feature

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 300


def _subagent_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _heartbeat_age_seconds(feature: "Feature", now: datetime) -> float | None:
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


def _is_stuck(feature: "Feature", now: datetime, heartbeat_timeout_seconds: int) -> bool:
    pid = getattr(feature, "subagent_pid", None)
    if pid is not None and _subagent_alive(pid):
        return False
    age = _heartbeat_age_seconds(feature, now)
    if age is None:
        return True
    return age >= heartbeat_timeout_seconds


def _reap(feature: "Feature", now: datetime) -> None:
    pid = getattr(feature, "subagent_pid", None)
    age = _heartbeat_age_seconds(feature, now)
    reap_count = (getattr(feature, "reap_count", None) or 0) + 1
    refinement_attempts = (getattr(feature, "refinement_attempts", None) or 0) + 1

    logger.info(
        "STUCK_REAPER: reaping feature %s (%s) — pid=%s heartbeat_age=%.0fs new_reap_count=%d",
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


def detect_and_reset_stuck_features(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Scan 'executing' features and reset those whose subagent is gone.

    Every orchestrator tick (or a dedicated 60s timer) should call this.
    Idempotent: resetting an already-reset feature is harmless.

    Args:
        project_id: UUID of the project to scan.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).

    Returns:
        List of feature IDs that were reaped (reset to 'ready').
    """
    now = datetime.now(timezone.utc)
    executing = db.list_features(project_id=project_id, status="executing")

    stuck = [f for f in executing if _is_stuck(f, now, heartbeat_timeout_seconds)]
    if not stuck:
        return []

    reaped_ids: list[str] = []
    for feature in stuck:
        try:
            _reap(feature, now)
            reaped_ids.append(feature.id)
        except Exception:
            logger.warning(
                "STUCK_REAPER: failed to reap feature %s; skipping",
                feature.id[:8],
                exc_info=True,
            )

    return reaped_ids


def detect_stuck_executing(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list["Feature"]:
    """Scan 'executing' features and return those whose subagent is gone.

    Delegates to bob.orchestrator.stuck_executing_reaper.find_stuck_features.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).
            Must be a non-negative integer.

    Returns:
        List of Feature objects that are stuck (subagent dead/missing).

    Raises:
        ValueError: If project_id is empty or heartbeat_timeout_seconds is negative.
    """
    if not project_id:
        raise ValueError("project_id must not be empty")
    if heartbeat_timeout_seconds < 0:
        raise ValueError(
            f"heartbeat_timeout_seconds must be >= 0, got {heartbeat_timeout_seconds}"
        )
    return find_stuck_features(
        project_id,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
    )


def reset_stuck_feature(
    feature: "Feature",
    now: datetime | None = None,
) -> None:
    """Reset a single stuck feature from 'executing' to 'ready'.

    Sets status='ready', increments refinement_attempts, stamps last_reap_at
    and increments reap_count, clears subagent_pid and subagent_heartbeat_at,
    and emits a structured log line with the prior PID and heartbeat age.

    Delegates to bob.orchestrator.stuck_executing_reaper.reap_stuck_feature.

    Args:
        feature: The Feature model instance to reap. Must not be None and must
            have an 'id' attribute.
        now: Reference timestamp (defaults to UTC now).

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            f"feature must have an 'id' attribute, got {type(feature).__name__}"
        )
    reap_stuck_feature(feature, now=now)


# Alias satisfying AC: "Function defined: bob.stuck_reaper.reap_stuck_executing"
reap_stuck_executing = reset_stuck_feature
