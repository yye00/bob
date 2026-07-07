"""Orchestrator dispatch concurrency — public entry points.

Feature 16743e36: let multiple ready features run in parallel instead of
strict single-flight.

A prior generation stall analysis found that the orchestrator dispatched one
feature at a time (a synchronous ``await execute_feature(feature)`` per
feature).  With ``max_turns`` per subagent and pytest verification taking
minutes, a single hung subagent could hold the whole round hostage even after
the watchdog cancelled it — the next ready row only started once cancellation
completed.

This module exposes the two stable public functions the orchestrator tick loop
calls to fan out concurrent dispatch:

:func:`max_concurrent_features`
    Resolve ``BOB_MAX_CONCURRENT_FEATURES`` (default 3, floor 1).

:func:`fill_ready_slots`
    Claim up to N ready features (N = open concurrency slots) and return them
    for concurrent dispatch, marking each ``executing`` so a parallel caller
    does not re-select the same feature.

Both delegate to the battle-tested implementations in
:mod:`bob.orchestrator.run_loop` so there is a single source of truth for the
claim/slot logic; this module is the thin, import-light seam the rest of the
codebase depends on.
"""

from __future__ import annotations

from typing import Any


def max_concurrent_features() -> int:
    """Return the configured maximum number of concurrently-dispatched features.

    Reads ``BOB_MAX_CONCURRENT_FEATURES`` from the environment, falling back to
    the default of 3.  A non-positive value is clamped to 1 and an
    unparseable value falls back to the default.  The return value is always
    ``>= 1`` so callers can use it directly as an ``asyncio.Semaphore`` bound.

    Returns:
        Integer ``>= 1`` — the concurrency cap.
    """
    from bob.orchestrator.run_loop import _resolve_max_concurrent_features

    return _resolve_max_concurrent_features()


def fill_ready_slots(
    loop: Any,
    *,
    active_feature_ids: "set[str] | None" = None,
) -> "list[Any]":
    """Claim ready features to fill the open concurrency slots on *loop*.

    Computes how many dispatch slots are open (cap minus in-flight features)
    and claims that many ``ready`` features from the loop's project, marking
    each ``executing`` so a parallel caller within the same tick does not
    re-select it.  Returns the claimed features for concurrent dispatch.

    Args:
        loop: An orchestration loop exposing ``max_concurrent_features`` and
            ``find_next_ready_feature()``.  Must not be ``None``.
        active_feature_ids: Optional set of feature IDs already in flight.
            Features whose IDs are in this set are skipped, and the set is used
            to compute the number of open slots.  ``None`` is treated as no
            in-flight work (all cap slots open).

    Returns:
        List of claimed feature objects to dispatch.  Empty when the cap is
        saturated or no ready features exist.

    Raises:
        ValueError: If *loop* is ``None``.
    """
    if loop is None:
        raise ValueError("loop must not be None")

    from bob.orchestrator.run_loop import dispatch_up_to_concurrency

    return dispatch_up_to_concurrency(loop, active_feature_ids=active_feature_ids)
