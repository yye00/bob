"""Exponential backoff after reaper-reset (7fa3f533).

When the stuck_executing_reaper resets a feature from 'executing' back to
'ready', the dispatch loop must not immediately re-dispatch the same feature —
the failure mode that caused the reap will likely recur on the very next
attempt.

This module provides:

  compute_backoff_seconds(reap_count)
      Backoff window in seconds: min(2^reap_count * 60, 3600).

  may_redispatch(feature, now)
      True if the feature's backoff window has elapsed since last_reap_at.

  escalate_after_n_reaps(feature_id, reap_count, threshold)
      If reap_count >= threshold (default 3), transition the feature to
      'needs_human' with reason="repeated_reap_cycle" and return True.

Integration: call escalate_after_n_reaps and may_redispatch from the dispatch
loop after the reaper stamps last_reap_at / reap_count on the row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob3 import db

if TYPE_CHECKING:
    from bob3.models import Feature

logger = logging.getLogger(__name__)

_DEFAULT_ESCALATION_THRESHOLD = 3
_BACKOFF_BASE_SECONDS = 60
_BACKOFF_CAP_SECONDS = 3600


def compute_backoff_seconds(reap_count: int) -> int:
    """Return the backoff window for a feature that has been reaped reap_count times.

    Formula: min(2^reap_count * 60, 3600)

    Args:
        reap_count: Number of times the feature has been reaped. Must be >= 0.

    Returns:
        Integer seconds in [60, 3600].
    """
    if reap_count < 0:
        reap_count = 0
    raw = (2 ** reap_count) * _BACKOFF_BASE_SECONDS
    return min(raw, _BACKOFF_CAP_SECONDS)


def may_redispatch(feature: "Feature", now: datetime | None = None) -> bool:
    """Return True if the feature's backoff window has elapsed since last_reap_at.

    A feature with reap_count == 0 or last_reap_at == None is always
    dispatchable (no prior reap has occurred).

    Args:
        feature: The Feature model instance to check.
        now: Reference time for the check (defaults to UTC now).

    Returns:
        True if the feature may be dispatched; False if within backoff window.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    last_reap_at = getattr(feature, "last_reap_at", None)
    reap_count = getattr(feature, "reap_count", 0) or 0

    if last_reap_at is None or reap_count == 0:
        return True

    if isinstance(last_reap_at, str):
        last_reap_at = datetime.fromisoformat(last_reap_at)

    if last_reap_at.tzinfo is None:
        last_reap_at = last_reap_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    elapsed = (now - last_reap_at).total_seconds()
    backoff = compute_backoff_seconds(reap_count)

    if elapsed < backoff:
        logger.debug(
            "Feature %s within backoff window: %.0fs elapsed / %ds required (reap_count=%d)",
            feature.id[:8], elapsed, backoff, reap_count,
        )
        return False
    return True


def escalate_after_n_reaps(
    feature_id: str,
    reap_count: int,
    threshold: int = _DEFAULT_ESCALATION_THRESHOLD,
) -> bool:
    """Escalate a feature to needs_human if it has been reaped >= threshold times.

    Stamps needs_human_reason="repeated_reap_cycle" via db.update_feature.

    Args:
        feature_id: UUID of the feature to escalate.
        reap_count: Current reap count on the feature row.
        threshold: Number of reaps required before escalation (default 3).

    Returns:
        True if the feature was escalated; False if below threshold.
    """
    if reap_count < threshold:
        return False

    logger.warning(
        "Feature %s has been reaped %d times (threshold=%d); escalating to needs_human",
        feature_id[:8], reap_count, threshold,
    )
    db.update_feature(
        feature_id,
        status="needs_human",
        last_improvement_type="repeated_reap_cycle",
    )
    return True
