"""Orchestrator dispatch concurrency — parallel ready-feature dispatch.

Feature: ed7d9fbb-233a-408e-a90f-3a4b5392cf8c

Introduces ``BOB3_MAX_CONCURRENT_FEATURES`` (default 3) so that up to N ready
features are dispatched as concurrent asyncio tasks per orchestrator tick.
Each task carries its own watchdog; one hung feature cannot block its peers.

The orchestrator tick loop uses::

    from bob3.orchestrator_concurrency import dispatch_concurrent_features

    results = await dispatch_concurrent_features(
        loop,
        worker=execute_feature,
        active_feature_ids=in_flight_ids,
    )

This module is the canonical import surface for concurrent dispatch.  The
implementation lives in :mod:`bob3.orchestrator.run_loop`; this module
re-exports it so callers can reference ``bob3.orchestrator_concurrency``
without touching the internal run-loop module directly.
"""

from __future__ import annotations

from bob3.orchestrator.run_loop import (
    _resolve_max_concurrent_features,
    current_concurrency_slots,
    dispatch_concurrent_features,
    dispatch_up_to_concurrency,
)

__all__ = [
    "dispatch_concurrent_features",
    "dispatch_up_to_concurrency",
    "current_concurrency_slots",
    "_resolve_max_concurrent_features",
]
