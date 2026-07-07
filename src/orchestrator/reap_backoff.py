"""orchestrator.reap_backoff — exponential backoff after reaper-reset (01d07a40).

Canonical ``orchestrator``-package entry point required by the feature AC:
  - orchestrator.reap_backoff.next_dispatch_allowed_at
  - orchestrator.reap_backoff.should_refuse_redispatch

The heavy backoff logic lives in ``bob.orchestrator.reap_backoff``; this module
re-exports it and adds ``next_dispatch_allowed_at``, the earliest wall-clock
time at which a recently-reaped feature may be re-dispatched.

Backoff window: ``min(2^reap_count * 60s, 3600s)`` measured from ``last_reap_at``.
A feature that has never been reaped (reap_count == 0 or last_reap_at is None) is
immediately dispatchable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob.orchestrator.reap_backoff import (  # noqa: F401 — re-exported for AC
    compute_backoff_seconds,
    escalate_after_n_reaps,
    may_redispatch,
)
from bob.reaper import should_refuse_redispatch  # noqa: F401 — re-exported for AC

if TYPE_CHECKING:
    from bob.models import Feature

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def next_dispatch_allowed_at(feature: "Feature") -> datetime:
    """Return the earliest UTC time at which *feature* may be re-dispatched.

    A feature that has never been reaped (reap_count == 0 or last_reap_at is
    None) may be dispatched immediately, so a past timestamp (the Unix epoch) is
    returned. Otherwise the returned time is
    ``last_reap_at + compute_backoff_seconds(reap_count)``.

    Naive ``last_reap_at`` values are interpreted as UTC.

    Args:
        feature: The Feature model instance to check.

    Returns:
        A timezone-aware UTC datetime.

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

    reap_count = getattr(feature, "reap_count", 0) or 0
    last_reap_at = getattr(feature, "last_reap_at", None)

    if reap_count == 0 or last_reap_at is None:
        return _EPOCH

    if isinstance(last_reap_at, str):
        last_reap_at = datetime.fromisoformat(last_reap_at)
    if last_reap_at.tzinfo is None:
        last_reap_at = last_reap_at.replace(tzinfo=timezone.utc)

    from datetime import timedelta

    return last_reap_at + timedelta(seconds=compute_backoff_seconds(reap_count))


__all__ = [
    "next_dispatch_allowed_at",
    "should_refuse_redispatch",
    "compute_backoff_seconds",
    "may_redispatch",
    "escalate_after_n_reaps",
]
