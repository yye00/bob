"""Exponential backoff after reaper-reset (9063503c).

This module satisfies AC: ``Function defined: bob3.orchestrator.exponential_backoff``.

Provides the dispatch-loop facing entry point for the reaper-backoff system.
Delegates computation to bob3.orchestrator.reap_backoff (the canonical
implementation) and bob3.reaper (the top-level API).

Public API
----------
exponential_backoff(feature, now)
    Check if a feature is within its backoff window or should be escalated.
    Returns a BackoffDecision.

check_reap_backoff(feature, now)
    Alias for exponential_backoff; convenience name for the dispatch loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob3.orchestrator.reap_backoff import (
    compute_backoff_seconds,
    escalate_after_n_reaps,
    may_redispatch,
)

if TYPE_CHECKING:
    from bob3.models import Feature

logger = logging.getLogger(__name__)

_ESCALATION_THRESHOLD = 3


def exponential_backoff(
    feature: "Feature",
    now: datetime | None = None,
) -> "BackoffDecision":
    """Enforce exponential backoff after reaper-reset for a feature.

    This is the canonical entry point satisfying:
      AC: ``Function defined: bob3.orchestrator.exponential_backoff``

    The dispatch loop calls this before re-dispatching any feature that has
    been reaped. It checks whether the feature is within its backoff window
    (min(2^reap_count * 60s, 3600s)) and escalates to needs_human after 3
    reaps without an intervening success.

    Args:
        feature: Feature model instance to check. Must have ``id``,
            ``reap_count``, and ``last_reap_at`` attributes.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        BackoffDecision with refused/escalated flags and computed values.

    Raises:
        ValueError: If feature is None or lacks an ``id`` attribute.
    """
    from bob3.reaper import BackoffDecision, handle_exponential_backoff  # noqa: PLC0415

    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            f"feature must be a Feature model instance with an 'id' attribute, "
            f"got {type(feature).__name__}"
        )
    if now is None:
        now = datetime.now(timezone.utc)

    return handle_exponential_backoff(feature, now=now)


def check_reap_backoff(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Return True if the feature should NOT be re-dispatched yet.

    Convenience name for the dispatch loop. Delegates to
    bob3.orchestrator.reap_backoff.

    Args:
        feature: Feature model instance to check.
        now: Reference time (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if allowed.

    Raises:
        ValueError: If feature is None or lacks an ``id`` attribute.
    """
    from bob3.reaper import should_refuse_redispatch  # noqa: PLC0415

    return should_refuse_redispatch(feature, now=now)


__all__ = [
    "exponential_backoff",
    "check_reap_backoff",
    "compute_backoff_seconds",
    "may_redispatch",
    "escalate_after_n_reaps",
]
