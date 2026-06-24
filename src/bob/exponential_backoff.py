"""Exponential backoff after reaper-reset — refuse re-dispatch of a recently reaped feature.

Feature c9b640d0: When the stuck_executing_reaper resets a feature from
'executing' to 'ready', the dispatch loop must not immediately re-dispatch the
same feature. The failure mode that caused the reap will recur immediately if
re-dispatched.

Fix: stamp last_reap_at and reap_count after each reap. The dispatch loop
refuses re-dispatch within min(2^reap_count * 60s, 3600s) of last_reap_at.
After 3 reaps without an intervening success, escalate to needs_human with
reason="repeated_reap_cycle".

Public API
----------
should_refuse_redispatch(feature, now)
    Return True if the feature is within its backoff window or should be
    escalated to needs_human. Delegates to bob.reaper.

stamp_reap_metadata(feature_id, reap_count, now)
    Stamp last_reap_at and reap_count on a feature row after a reap event.
    Delegates to bob.reaper.stamp_reap_metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob.orchestrator.reap_backoff import compute_backoff_seconds as _compute_backoff_seconds
from bob.reaper import (
    BackoffDecision,
    handle_exponential_backoff,
    should_refuse_redispatch as _reaper_should_refuse_redispatch,
    stamp_reap_metadata as _reaper_stamp_reap_metadata,
)
from bob.reaper_backoff import calculate_backoff_delay as _calculate_backoff_delay

if TYPE_CHECKING:
    from bob.models import Feature


def calculate_backoff_duration(reap_count: int) -> int:
    """Return the backoff window in seconds for a given reap count.

    Formula: min(2^reap_count * 60, 3600)

    Args:
        reap_count: Number of times the feature has been reaped. Must be an int >= 0.

    Returns:
        Integer seconds in [60, 3600].

    Raises:
        TypeError: If reap_count is not an integer type.
    """
    if not isinstance(reap_count, int):
        raise TypeError(f"reap_count must be an int, got {type(reap_count).__name__}")
    return _compute_backoff_seconds(reap_count)


def should_refuse_redispatch(
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
    return _reaper_should_refuse_redispatch(feature, now=now)


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
    _reaper_stamp_reap_metadata(feature_id, reap_count, now=now)


def calculate_backoff_delay(reap_count: int) -> int:
    """Return the backoff delay in seconds for a feature reaped reap_count times.

    Formula: min(2^reap_count * 60, 3600)

    This is the AC-mandated name for the backoff calculation function.
    Delegates to bob.reaper_backoff.calculate_backoff_delay.

    Args:
        reap_count: Number of times the feature has been reaped.
                    Negative values are treated as 0.

    Returns:
        Integer seconds in [60, 3600].

    Raises:
        TypeError: If reap_count is not an integer type (e.g., string, list, None).
    """
    return _calculate_backoff_delay(reap_count)


def should_allow_dispatch(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature IS allowed to be re-dispatched right now.

    This is the logical inverse of should_refuse_redispatch. A feature may be
    dispatched when it is outside its backoff window AND has not exceeded the
    escalation threshold (< 3 reaps without intervening success).

    Args:
        feature: The Feature model instance to check. Must not be None and must
            have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch is allowed; False if dispatch should be refused.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    return not _reaper_should_refuse_redispatch(feature, now=now)


def should_backoff_from_reap(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature should be held back from re-dispatch due to reap backoff.

    This is an alias for should_refuse_redispatch with an AC-mandated name.
    A feature should back off when:
    1. It has been reaped >= 3 times without success — escalated to needs_human.
    2. It is within the exponential backoff window: min(2^reap_count * 60s, 3600s).

    Args:
        feature: The Feature model instance to check. Must not be None and must
            have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    return _reaper_should_refuse_redispatch(feature, now=now)


def record_reap(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Record that a feature has been reaped — stamp last_reap_at and reap_count.

    This is an alias for stamp_reap_metadata with an AC-mandated name.
    Called by the stuck_executing_reaper immediately after resetting a feature
    to 'ready'. These two fields are the persistent memory that the dispatch
    loop uses to enforce exponential backoff.

    Args:
        feature_id: UUID of the feature that was reaped.
        reap_count: New (post-reap) reap_count to write.
        now: Timestamp to use as last_reap_at (defaults to UTC now).
    """
    _reaper_stamp_reap_metadata(feature_id, reap_count, now=now)


def check_reap_backoff(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature should NOT be re-dispatched right now.

    AC-mandated entry point for the dispatch loop. Returns True when the
    feature is within the exponential backoff window or has been escalated
    to needs_human due to repeated reap cycles.

    Formula: refuse within min(2^reap_count * 60s, 3600s) of last_reap_at.
    Escalate to needs_human after 3 reaps without an intervening success.

    Args:
        feature: The Feature model instance to check. Must not be None and
            must have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    return _reaper_should_refuse_redispatch(feature, now=now)


def should_dispatch_after_reap(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature IS allowed to be dispatched after a prior reap.

    This is the AC-mandated function. Returns True when the feature is
    outside its exponential backoff window AND has not exceeded the escalation
    threshold. Equivalent to the logical inverse of should_refuse_redispatch.

    Formula: allow dispatch when elapsed >= min(2^reap_count * 60s, 3600s)
    since last_reap_at. Never allow when reap_count >= 3.

    Args:
        feature: The Feature model instance to check. Must not be None and
            must have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch is allowed; False if dispatch should be refused.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
        TypeError: If feature is not an object with an 'id' attribute.
    """
    return not _reaper_should_refuse_redispatch(feature, now=now)


def compute_reap_backoff_time(reap_count: int) -> int:
    """Return the backoff window in seconds for a given reap count.

    AC-mandated name for the backoff duration calculation.
    Formula: min(2^reap_count * 60, 3600).

    Args:
        reap_count: Number of times the feature has been reaped.
            Negative values are treated as 0. Must be an integer.

    Returns:
        Integer seconds in [60, 3600].

    Raises:
        TypeError: If reap_count is not an integer type (e.g., string, list, None).
    """
    if not isinstance(reap_count, int):
        raise TypeError(f"reap_count must be an int, got {type(reap_count).__name__}")
    return _compute_backoff_seconds(reap_count)


def record_reap_event(
    feature_id: str,
    reap_count: int,
    now: datetime | None = None,
) -> None:
    """Record a reap event — stamp last_reap_at and reap_count on the feature row.

    AC-mandated name for the reap stamping operation. Called by the
    stuck_executing_reaper immediately after resetting a feature to 'ready'.
    These two fields are the persistent memory that the dispatch loop uses
    to enforce exponential backoff and detect repeated reap cycles.

    Args:
        feature_id: UUID of the feature that was reaped.
        reap_count: New (post-reap) reap_count to write.
        now: Timestamp to use as last_reap_at (defaults to UTC now).
    """
    _reaper_stamp_reap_metadata(feature_id, reap_count, now=now)


# AC-mandated alias: "Function defined: bob.exponential_backoff.should_allow_redispatch"
should_allow_redispatch = should_allow_dispatch

__all__ = [
    "calculate_backoff_delay",
    "calculate_backoff_duration",
    "check_reap_backoff",
    "compute_reap_backoff_time",
    "record_reap_event",
    "should_allow_dispatch",
    "should_allow_redispatch",
    "should_dispatch_after_reap",
    "should_refuse_redispatch",
    "should_backoff_from_reap",
    "stamp_reap_metadata",
    "record_reap",
    "BackoffDecision",
]
