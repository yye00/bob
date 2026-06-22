"""Dispatch backoff — refuse re-dispatch of a recently reaped feature.

Feature d39bdcdb: Exponential backoff after reaper-reset.

When the stuck_executing_reaper resets a feature from 'executing' to 'ready',
the dispatch loop must refuse to re-dispatch the feature within the backoff
window min(2^reap_count * 60s, 3600s). After 3 reaps without an intervening
success, the feature is escalated to needs_human with reason="repeated_reap_cycle".

Public API
----------
should_refuse_recent_reap(feature, now)
    Return True if the feature is within its backoff window or should be
    escalated. Delegates to bob3.reaper for the heavy logic.

stamp_reap_metadata(feature_id, reap_count, now)
    Stamp last_reap_at and reap_count on a feature row after a reap event.
    Delegates to bob3.reaper.stamp_reap_metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob3.models import Feature


def should_refuse_recent_reap(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature should NOT be re-dispatched right now.

    A feature should be refused re-dispatch when:
    1. It has been reaped >= 3 times without an intervening success — in that
       case it is escalated to needs_human and refused.
    2. It is within the exponential backoff window since last_reap_at, computed
       as min(2^reap_count * 60s, 3600s).

    Args:
        feature: The Feature model instance to check. Must not be None and must
            have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            f"feature must be a Feature model instance with an 'id' attribute, "
            f"got {type(feature).__name__}"
        )
    if now is None:
        now = datetime.now(timezone.utc)

    from bob3.reaper import should_refuse_redispatch  # noqa: PLC0415

    return should_refuse_redispatch(feature, now=now)


def stamp_reap_metadata(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Stamp last_reap_at and reap_count on a feature row after a reap event.

    Called by the stuck_executing_reaper after resetting a feature to 'ready'.
    These two fields are the persistent memory used by the dispatch loop to
    enforce exponential backoff via should_refuse_recent_reap.

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

    from bob3.reaper import stamp_reap_metadata as _stamp  # noqa: PLC0415

    _stamp(feature_id, reap_count=reap_count, now=now)


__all__ = [
    "should_refuse_recent_reap",
    "stamp_reap_metadata",
]
