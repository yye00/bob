"""bob75 reaper module — exponential backoff after reaper-reset (F-R7-511).

Provides the bob75-namespace surface for the exponential backoff enforcement
that prevents the dispatch loop from immediately re-dispatching a recently
reaped feature.

Satisfies ACs:
  - File exists: src/bob75/reaper.py
  - Function defined: bob75.reaper.should_refuse_redispatch
  - Function defined: bob75.reaper.calculate_backoff_delay

The heavy logic lives in bob.reaper and bob.orchestrator.reap_backoff;
this module re-exports the canonical API at the bob75 namespace level.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob.orchestrator.reap_backoff import compute_backoff_seconds
from bob.reaper import (  # noqa: F401 — re-exported
    BackoffDecision,
    handle_exponential_backoff,
    should_refuse_redispatch,
    stamp_reap_metadata,
)

if TYPE_CHECKING:
    from bob.models import Feature


def calculate_backoff_delay(reap_count: int) -> int:
    """Return the backoff delay in seconds for a feature reaped reap_count times.

    Formula: min(2^reap_count * 60, 3600)

    This is the canonical bob75-namespace entry point for the backoff formula.
    Delegates to bob.orchestrator.reap_backoff.compute_backoff_seconds.

    Args:
        reap_count: Number of times the feature has been reaped. Must be >= 0.
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
    return compute_backoff_seconds(reap_count)


__all__ = [
    "BackoffDecision",
    "calculate_backoff_delay",
    "handle_exponential_backoff",
    "should_refuse_redispatch",
    "stamp_reap_metadata",
]
