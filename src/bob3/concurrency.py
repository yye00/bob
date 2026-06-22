"""Public concurrency API for Bob3 orchestrator dispatch (feature 083b89c4).

Exposes the concurrent dispatch primitives used by the orchestration loop
to run multiple ready features in parallel instead of strict single-flight.

The key knob is ``BOB3_MAX_CONCURRENT_FEATURES`` (default 3): set it to
control how many features may be in flight simultaneously.  Each in-flight
feature carries its own watchdog; a single hung or failing feature cannot
block the others.

Exports
-------
resolve_max_concurrent_features
    Read the concurrency cap from the environment.
dispatch_concurrent_features
    Primary tick-loop entry point: claim + dispatch up to N ready features.
run_concurrent
    Lower-level bounded-concurrency gather with failure isolation.
"""

from __future__ import annotations

from bob3.orchestrator.concurrent_executor import run_concurrent
from bob3.orchestrator.run_loop import (
    _resolve_max_concurrent_features as resolve_max_concurrent_features,
    dispatch_concurrent_features,
    dispatch_up_to_concurrency,
    current_concurrency_slots,
)

__all__ = [
    "dispatch_concurrent_features",
    "dispatch_up_to_concurrency",
    "current_concurrency_slots",
    "resolve_max_concurrent_features",
    "run_concurrent",
]
