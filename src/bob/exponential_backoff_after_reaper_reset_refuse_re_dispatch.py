"""Exponential backoff after reaper-reset — refuse re-dispatch of a recently reaped feature.

Feature 769a08d6: When the stuck_executing_reaper resets a feature from 'executing'
to 'ready', the dispatch loop must not immediately re-dispatch the same feature.
The failure mode that caused the reap will recur immediately if re-dispatched.

This module provides the top-level entry point
``exponential_backoff_after_reaper_reset_refuse_re_dispatch`` that integrates:

1. Stamping reap metadata (last_reap_at, reap_count) after a reap event.
2. Enforcing exponential backoff: refuse re-dispatch within min(2^N * 60s, 3600s).
3. Escalating to needs_human after 3 reaps without an intervening success.

Delegates to bob.reaper for the heavy logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob.reaper import BackoffDecision, handle_exponential_backoff, stamp_reap_metadata

if TYPE_CHECKING:
    from bob.models import Feature


def exponential_backoff_after_reaper_reset_refuse_re_dispatch(
    feature: "Feature",
    now: datetime | None = None,
) -> BackoffDecision:
    """Enforce exponential backoff and escalation for a recently-reaped feature.

    When the stuck_executing_reaper resets a feature row to 'ready', the dispatch
    loop calls this function before dispatching. It returns a BackoffDecision
    indicating whether dispatch should proceed or be refused.

    Backoff formula: min(2^reap_count * 60s, 3600s).
    Escalation: after reap_count >= 3, the feature is transitioned to
    needs_human with reason="repeated_reap_cycle".

    Args:
        feature: Feature model instance to check. Must have ``reap_count`` and
                 ``last_reap_at`` attributes stamped by the reaper.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        BackoffDecision with:
          - refused: True if dispatch should be refused.
          - escalated: True if the feature was transitioned to needs_human.
          - reap_count: Current reap count on the feature.
          - backoff_seconds: Computed backoff window in seconds.
          - reason: "escalated" | "within_window" | "allowed".
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return handle_exponential_backoff(feature, now=now)


__all__ = [
    "exponential_backoff_after_reaper_reset_refuse_re_dispatch",
    "stamp_reap_metadata",
    "BackoffDecision",
]
