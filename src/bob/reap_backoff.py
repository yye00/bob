"""Exponential backoff after reaper-reset (f6ec0c94).

AC-named façade for the dispatch-loop half of the reaper backoff feature.

When the stuck_executing_reaper resets a feature from 'executing' back to
'ready', the dispatch loop must refuse to re-dispatch that feature until
``min(2^reap_count * 60s, 3600s)`` has elapsed since ``last_reap_at``. After 3
reaps without an intervening success the feature is escalated to needs_human
with reason "repeated_reap_cycle".

The backoff math and escalation live in ``bob.orchestrator.reap_backoff``; the
refuse/escalate decision lives in ``bob.reaper``. This module re-exports those
under the AC-required names and adds ``next_reap_dispatch_delay`` — the number of
seconds the dispatch loop should still wait before re-dispatching a feature.

Integration: ``bob.supervisor_loop`` consults ``should_refuse_redispatch`` before
resuming a reaped-then-reset feature.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob.orchestrator.reap_backoff import (  # noqa: F401 — re-exported for AC/integration
    compute_backoff_seconds,
    escalate_after_n_reaps,
    may_redispatch,
)
from bob.reaper import should_refuse_redispatch  # noqa: F401 — re-exported for AC

if TYPE_CHECKING:
    from bob.models import Feature


def next_reap_dispatch_delay(feature: "Feature", now: datetime | None = None) -> int:
    """Return the seconds still to wait before *feature* may be re-dispatched.

    Zero means the backoff window has elapsed (or the feature was never reaped),
    so the dispatch loop may proceed immediately. A positive value is the
    remaining backoff, computed as
    ``compute_backoff_seconds(reap_count) - (now - last_reap_at)``.

    Args:
        feature: The Feature model instance to check.
        now: Reference time for the check (defaults to UTC now).

    Returns:
        Non-negative integer seconds remaining in the backoff window.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            "feature must be a Feature model instance with an 'id' attribute, "
            f"got {type(feature).__name__}"
        )

    if now is None:
        now = datetime.now(timezone.utc)

    reap_count = getattr(feature, "reap_count", 0) or 0
    last_reap_at = getattr(feature, "last_reap_at", None)

    if reap_count == 0 or last_reap_at is None:
        return 0

    if isinstance(last_reap_at, str):
        last_reap_at = datetime.fromisoformat(last_reap_at)
    if last_reap_at.tzinfo is None:
        last_reap_at = last_reap_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    elapsed = (now - last_reap_at).total_seconds()
    remaining = compute_backoff_seconds(reap_count) - elapsed
    if remaining <= 0:
        return 0
    return int(remaining)


__all__ = [
    "next_reap_dispatch_delay",
    "should_refuse_redispatch",
    "compute_backoff_seconds",
    "may_redispatch",
    "escalate_after_n_reaps",
]
