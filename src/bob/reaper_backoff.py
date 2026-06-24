"""Exponential backoff after reaper-reset (97e58db1).

Provides the top-level bob.reaper_backoff module required by the feature ACs:
  - Function defined: bob.reaper_backoff.calculate_backoff_delay
  - Function defined: bob.reaper_backoff.should_refuse_redispatch

Self-contained: implements the backoff formula directly to avoid circular imports.

Backoff formula: min(2^reap_count * 60, 3600).
Escalation: after reap_count >= 3 without intervening success, escalate
feature to needs_human with reason="repeated_reap_cycle".

IMPORT ISOLATION: This module is imported by bob.orchestrator.__init__, which
is itself imported by bob.orchestrator.reap_backoff. Therefore this module
must NOT import from bob.orchestrator at module load time. All logic is
implemented locally; heavier bob.reaper objects are lazy-loaded via __getattr__.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob.models import Feature

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 60
_BACKOFF_CAP_SECONDS = 3600
_ESCALATION_THRESHOLD = 3


def _compute_backoff_seconds(reap_count: int) -> int:
    """Return backoff window in seconds: min(2^reap_count * 60, 3600)."""
    if reap_count < 0:
        reap_count = 0
    return min((2 ** reap_count) * _BACKOFF_BASE_SECONDS, _BACKOFF_CAP_SECONDS)


def calculate_backoff_delay(reap_count: int) -> int:
    """Return the backoff delay in seconds for a feature reaped reap_count times.

    Formula: min(2^reap_count * 60, 3600)

    Args:
        reap_count: Number of times the feature has been reaped.
                    Negative values are treated as 0.

    Returns:
        Integer seconds in [60, 3600].

    Raises:
        TypeError: If reap_count is not an integer type (e.g., string, list, None).
    """
    if not isinstance(reap_count, int):
        raise TypeError(
            f"reap_count must be an int, got {type(reap_count).__name__!r}"
        )
    return _compute_backoff_seconds(reap_count)


def should_refuse_redispatch(feature: "Feature", now: datetime | None = None) -> bool:
    """Return True if the feature should not be re-dispatched yet.

    Implements the backoff check inline to avoid circular imports with
    bob.orchestrator. Escalation is performed via a lazy import of bob.db.

    Args:
        feature: The Feature model instance to check.
        now: Reference time (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if allowed.
    """
    reap_count = getattr(feature, "reap_count", 0) or 0

    # Escalate to needs_human after threshold reaps regardless of window
    if reap_count >= _ESCALATION_THRESHOLD:
        import bob.db as _db  # noqa: PLC0415 — lazy to avoid circular import
        _db.update_feature(
            feature.id,
            status="needs_human",
            last_improvement_type="repeated_reap_cycle",
        )
        logger.warning(
            "Feature %s escalated to needs_human after %d reaps",
            feature.id, reap_count,
        )
        return True

    last_reap_at = getattr(feature, "last_reap_at", None)
    if last_reap_at is None:
        return False

    if now is None:
        now = datetime.now(timezone.utc)

    if isinstance(last_reap_at, str):
        last_reap_at = datetime.fromisoformat(last_reap_at)
    if last_reap_at.tzinfo is None:
        last_reap_at = last_reap_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    elapsed = (now - last_reap_at).total_seconds()
    backoff = _compute_backoff_seconds(reap_count)
    return elapsed < backoff


def __getattr__(name: str):
    """Lazy re-exports from bob.reaper to avoid circular imports at load time."""
    if name in ("BackoffDecision", "handle_exponential_backoff"):
        import bob.reaper as _reaper  # noqa: PLC0415
        return getattr(_reaper, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "calculate_backoff_delay",
    "should_refuse_redispatch",
    "BackoffDecision",
    "handle_exponential_backoff",
]
