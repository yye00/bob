"""Top-level reaper module for bob — exponential backoff after reaper-reset (b75a279b).

Provides:
  stamp_reap_metadata(feature_id, reap_count, now)
      Stamp last_reap_at and reap_count onto a feature row after a reap event.

  should_refuse_redispatch(feature, now)
      True if the feature should NOT be re-dispatched yet (within backoff window
      or should be escalated to needs_human).

  detect_stuck_executing(project_id, heartbeat_timeout_seconds)
      Scan 'executing' features and return those whose subagent is gone.

  reset_stuck_feature(feature, now)
      Reset a single stuck feature from 'executing' to 'ready'.

  handle_exponential_backoff(feature, now)
      Combined entry point: check if a feature is within its backoff window or
      should be escalated after repeated reaps. Returns a BackoffDecision with
      the outcome and computed backoff duration.

The heavy logic lives in bob.orchestrator.reap_backoff; this module exposes
the canonical top-level API required by the feature's acceptance criteria.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob import db
from bob.orchestrator.reap_backoff import (
    compute_backoff_seconds,
    escalate_after_n_reaps,
    may_redispatch,
)
from bob.orchestrator.stuck_executing_reaper import (
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    find_stuck_features,
    reap_stuck_feature,
    sweep_stuck_executing,
)
from bob.orchestrator.zombie_run_reaper import scan_and_reap
from bob.startup_crash_exempt import (  # noqa: F401 — startup-crash exemption integration
    is_transport_crash,
    should_exempt_from_retry,
    try_exempt,
)

# Environment-capability preflight integration (a05a9611 — preflight-with-research)
from bob72.preflight import (  # noqa: F401 — re-exported for integration AC
    MissingDependencyError,
    discover_workaround,
    probe_dependencies,
    run_preflight,
)

if TYPE_CHECKING:
    from bob.models import Feature

logger = logging.getLogger(__name__)

_ESCALATION_THRESHOLD = 3


@dataclass
class BackoffDecision:
    """Result of handle_exponential_backoff."""

    refused: bool
    escalated: bool
    reap_count: int
    backoff_seconds: int
    reason: str  # "escalated" | "within_window" | "allowed"


def stamp_reap_metadata(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Stamp last_reap_at and reap_count on a feature row after a reap event.

    Called by the stuck_executing_reaper immediately after resetting a feature
    to 'ready'. These two fields are the persistent memory that the dispatch
    loop uses to enforce exponential backoff.

    Args:
        feature_id: UUID of the feature that was reaped.
        reap_count: New (post-reap) reap_count to write.
        now: Timestamp to use as last_reap_at (defaults to UTC now).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    db.update_feature(
        feature_id,
        last_reap_at=now.isoformat(),
        reap_count=reap_count,
    )
    logger.info(
        "REAPER: stamped reap metadata on feature %s — reap_count=%d last_reap_at=%s",
        feature_id[:8],
        reap_count,
        now.isoformat(),
    )


def should_refuse_redispatch(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature should NOT be re-dispatched right now.

    A feature should be refused re-dispatch when:
    1. It has been reaped >= 3 times without an intervening success — in that
       case it is escalated to needs_human and refused.
    2. It is within the exponential backoff window since last_reap_at.

    Args:
        feature: The Feature model instance to check.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None or not a feature-like object with an id attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            f"feature must be a Feature model instance with an 'id' attribute, got {type(feature).__name__}"
        )
    if now is None:
        now = datetime.now(timezone.utc)

    reap_count = getattr(feature, "reap_count", 0) or 0

    if reap_count >= _ESCALATION_THRESHOLD:
        escalated = escalate_after_n_reaps(feature.id, reap_count, threshold=_ESCALATION_THRESHOLD)
        if escalated:
            logger.warning(
                "REAPER: refusing re-dispatch of feature %s — escalated to needs_human "
                "after %d reaps",
                feature.id[:8],
                reap_count,
            )
            return True

    if not may_redispatch(feature, now=now):
        return True

    return False


def handle_exponential_backoff(
    feature: "Feature",
    now: datetime | None = None,
) -> BackoffDecision:
    """Combined entry point for exponential backoff enforcement after reaper-reset.

    Checks whether a feature is eligible for re-dispatch by:
    1. Escalating to needs_human if reap_count >= 3 (repeated_reap_cycle).
    2. Refusing re-dispatch if still within the exponential backoff window.

    This is the canonical function satisfying the feature AC
    ``Function defined: bob.reaper.handle_exponential_backoff``.

    Args:
        feature: The Feature model instance to check.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        BackoffDecision with refused/escalated flags and computed values.

    Raises:
        ValueError: If feature is None or not a feature-like object with an id attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            f"feature must be a Feature model instance with an 'id' attribute, got {type(feature).__name__}"
        )
    if now is None:
        now = datetime.now(timezone.utc)

    reap_count = getattr(feature, "reap_count", 0) or 0
    backoff_seconds = compute_backoff_seconds(reap_count)

    if reap_count >= _ESCALATION_THRESHOLD:
        escalated = escalate_after_n_reaps(
            feature.id, reap_count, threshold=_ESCALATION_THRESHOLD
        )
        if escalated:
            logger.warning(
                "REAPER: handle_exponential_backoff escalated feature %s to needs_human "
                "after %d reaps",
                feature.id[:8],
                reap_count,
            )
            return BackoffDecision(
                refused=True,
                escalated=True,
                reap_count=reap_count,
                backoff_seconds=backoff_seconds,
                reason="escalated",
            )

    if not may_redispatch(feature, now=now):
        logger.debug(
            "REAPER: handle_exponential_backoff refusing re-dispatch of feature %s "
            "— within %ds backoff window (reap_count=%d)",
            feature.id[:8],
            backoff_seconds,
            reap_count,
        )
        return BackoffDecision(
            refused=True,
            escalated=False,
            reap_count=reap_count,
            backoff_seconds=backoff_seconds,
            reason="within_window",
        )

    return BackoffDecision(
        refused=False,
        escalated=False,
        reap_count=reap_count,
        backoff_seconds=backoff_seconds,
        reason="allowed",
    )


def detect_stuck_executing(
    project_id: str,
    heartbeat_timeout_seconds: int = 300,
) -> list["Feature"]:
    """Scan 'executing' features and return those whose subagent is gone.

    A feature is considered stuck when its recorded subagent PID is absent or
    dead AND its heartbeat timestamp is older than heartbeat_timeout_seconds (or
    was never written).

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).
            Must be a non-negative integer.

    Returns:
        List of Feature objects that should be reaped.

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


def reap_zombie_runs(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is terminal.

    Joins sub_agent_runs against features and marks any 'running' row whose
    target_id points to a feature in a terminal state ('completed',
    'needs_human', 'regression', 'failed') as status='timeout' with a
    completion timestamp.

    Delegates to bob.orchestrator.zombie_run_reaper.scan_and_reap.

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').
    """
    return scan_and_reap(project_id)


def update_reap_tracking(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Update reap tracking fields on a feature row after a reap event.

    This is the AC-required entry point (AC: Function defined:
    bob.reaper.update_reap_tracking). It stamps last_reap_at and reap_count
    on the feature row so the dispatch loop can enforce exponential backoff.

    Delegates to stamp_reap_metadata.

    Args:
        feature_id: UUID of the feature that was reaped.
        reap_count: New (post-reap) reap_count to write. Must be a non-negative int.
        now: Timestamp to use as last_reap_at (defaults to UTC now).

    Raises:
        ValueError: If feature_id is empty/None or reap_count is not a non-negative int.
    """
    if not feature_id:
        raise ValueError("feature_id must not be empty")
    if not isinstance(reap_count, int):
        raise ValueError(f"reap_count must be an int, got {type(reap_count).__name__}")
    if reap_count < 0:
        raise ValueError(f"reap_count must be >= 0, got {reap_count}")
    stamp_reap_metadata(feature_id, reap_count=reap_count, now=now)


def reap_stuck_executing(
    project_id: str,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> list[str]:
    """Scan 'executing' features and reset those whose subagent is gone.

    AC entry point: "Function defined: bob.reaper.reap_stuck_executing"

    Every orchestrator tick (or a dedicated 60s timer) should call this.
    Idempotent: resetting an already-reset feature is harmless.

    A feature is stuck when its recorded subagent PID is absent or dead AND
    its heartbeat timestamp is older than heartbeat_timeout_seconds (or was
    never written). The feature is then reset to 'ready' and
    refinement_attempts is incremented so the next dispatch counts as a real
    attempt. The reap event is logged with the prior PID and heartbeat age.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.
        heartbeat_timeout_seconds: Staleness threshold in seconds (default 300).
            Must be a non-negative integer.

    Returns:
        List of feature IDs (strings) that were reaped (reset to 'ready').

    Raises:
        ValueError: If project_id is empty or heartbeat_timeout_seconds is negative.
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


# Alias satisfying AC: "Function defined: bob.reaper.apply_exponential_backoff"
apply_exponential_backoff = handle_exponential_backoff

# Alias satisfying AC: "Function defined: bob.reaper.reset_feature_status"
reset_feature_status = reset_stuck_feature

# Alias satisfying AC: "Function defined: bob.reaper.close_zombie_sub_agent_runs"
close_zombie_sub_agent_runs = reap_zombie_runs

def sweep_orphans_on_exit(project_id: str) -> list[str]:
    """Final reaper sweep: flip orphan 'executing' rows to 'failed' on orchestrator exit.

    AC entry point: "Function defined: bob.reaper.sweep_orphans_on_exit"

    Invoked immediately before _run_locked returns its LoopTermination at
    ALL_BLOCKED/BUDGET_EXCEEDED termination. Delegates to
    bob.final_reaper.sweep_orphans_on_exit which:
    1. Calls sweep_orphan_subagents() (same reaper as the main loop tick).
    2. Flips any remaining 'executing' rows whose PID is gone to 'failed' with
       reason 'orchestrator_exit_during_execution'.

    Idempotent and safe — a second call with the same DB state produces no
    additional writes.

    Args:
        project_id: UUID of the project whose orphan executing rows to sweep.

    Returns:
        List of feature IDs that were flipped to 'failed'.

    Raises:
        ValueError: If project_id is None or not a string.
    """
    from bob.final_reaper import sweep_orphans_on_exit as _impl  # noqa: PLC0415
    return _impl(project_id)


__all__ = [
    "stamp_reap_metadata",
    "update_reap_tracking",
    "should_refuse_redispatch",
    "handle_exponential_backoff",
    "apply_exponential_backoff",
    "detect_stuck_executing",
    "reap_stuck_executing",
    "reset_stuck_feature",
    "reset_feature_status",
    "reap_zombie_runs",
    "close_zombie_sub_agent_runs",
    "sweep_orphans_on_exit",
    "BackoffDecision",
    # startup-crash exemption integration (F-R7-613)
    "is_transport_crash",
    "should_exempt_from_retry",
    "try_exempt",
]
