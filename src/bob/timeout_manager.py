"""Per-feature wall-clock timeout manager for bob (feature 82111543).

Provides :class:`TimeoutManager` — a thin façade over :mod:`bob.timeout`
that exposes the per-feature hard wall-clock timeout as an importable,
named module so callers do not need to reach into lower-level internals.

Environment variable
--------------------
``BOB_FEATURE_TIMEOUT_SECONDS`` (float, seconds) — hard deadline per feature
attempt.  Defaults to 1800 s (30 min), which is generous enough for large
sub-agent runs while remaining finite so a wedged feature can never hold an
executing slot indefinitely.
"""

from __future__ import annotations

from bob.timeout import (
    FeatureTimeoutError,
    FeatureTimeoutManager,
    enforce_feature_timeout,
    enforce_wall_clock_timeout,
    resolve_timeout_seconds,
)

# Re-export the canonical manager under the expected module path.
TimeoutManager = FeatureTimeoutManager

__all__ = [
    "FeatureTimeoutError",
    "FeatureTimeoutManager",
    "TimeoutManager",
    "enforce_feature_timeout",
    "enforce_wall_clock_timeout",
    "resolve_timeout_seconds",
]
