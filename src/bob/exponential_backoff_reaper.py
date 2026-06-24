"""Exponential backoff after reaper-reset — refuse re-dispatch of a recently reaped feature.

Feature 265ff52b: When the stuck_executing_reaper resets a feature from 'executing'
to 'ready', the dispatch loop must not immediately re-dispatch the same feature.

The failure mode that caused the reap will recur immediately if re-dispatched.
This module provides the canonical entry points:

  calculate_backoff_delay(reap_count)
      Backoff window in seconds: min(2^reap_count * 60, 3600).

  should_refuse_redispatch(feature, now)
      True if the feature should NOT be re-dispatched yet (within backoff window
      or reap_count >= 3 triggers escalation to needs_human).

Integration: bob.dispatch calls these functions before dispatching any feature.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob.orchestrator.reap_backoff import (
    compute_backoff_seconds,
    escalate_after_n_reaps,
    may_redispatch,
)

if TYPE_CHECKING:
    from bob.models import Feature

_ESCALATION_THRESHOLD = 3
_BACKOFF_BASE_SECONDS = 60
_BACKOFF_CAP_SECONDS = 3600


def calculate_backoff_delay(reap_count: int) -> int:
    """Return the exponential backoff delay in seconds for a reaped feature.

    Formula: min(2^reap_count * 60, 3600).

    A reap_count of 0 returns the base 60s. Negative values are treated as 0.
    The result is capped at 3600s (1 hour) regardless of reap_count.

    Args:
        reap_count: Number of times the feature has been reaped. Must be int >= 0.

    Returns:
        Integer seconds in [60, 3600].

    Raises:
        TypeError: If reap_count is not an integer type.
        ValueError: If reap_count is None.
    """
    if reap_count is None:
        raise TypeError("reap_count must not be None")
    if not isinstance(reap_count, int):
        raise TypeError(
            f"reap_count must be an integer, got {type(reap_count).__name__}"
        )
    return compute_backoff_seconds(reap_count)


def should_refuse_redispatch(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature should NOT be re-dispatched right now.

    A feature is refused re-dispatch when:
    1. Its reap_count >= 3 (threshold) — escalated to needs_human with
       reason="repeated_reap_cycle", and dispatch is refused.
    2. It is within the exponential backoff window since last_reap_at.

    Features with reap_count == 0 or no last_reap_at are always allowed.

    Args:
        feature: The Feature model instance to check. Must have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None.
        AttributeError: If feature lacks an 'id' attribute.
        TypeError: If feature is not a feature-like object.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if isinstance(feature, (str, int, float, bytes)):
        raise TypeError(
            f"feature must be a Feature model instance, got {type(feature).__name__}"
        )
    if not hasattr(feature, "id"):
        raise AttributeError(
            f"feature must have an 'id' attribute, got {type(feature).__name__}"
        )
    if now is None:
        now = datetime.now(timezone.utc)

    reap_count = getattr(feature, "reap_count", 0) or 0

    if reap_count >= _ESCALATION_THRESHOLD:
        escalated = escalate_after_n_reaps(
            feature.id, reap_count, threshold=_ESCALATION_THRESHOLD
        )
        if escalated:
            return True

    return not may_redispatch(feature, now=now)


# AC alias: "Function defined: bob.exponential_backoff_reaper.calculate_backoff_duration"
calculate_backoff_duration = calculate_backoff_delay

__all__ = [
    "calculate_backoff_delay",
    "calculate_backoff_duration",
    "should_refuse_redispatch",
]
