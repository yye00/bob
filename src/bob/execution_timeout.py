"""Per-feature hard wall-clock execution timeout (feature f3a3f1c8).

Exposes :func:`enforce_feature_timeout` as the canonical module-level entry
point for bounding how long a single feature's sub-agent may run.  A hung
feature MUST NOT be able to hold an executing slot indefinitely — this module
ensures that guarantee is reachable from a stable import path regardless of
orchestrator internals.

Timeout resolution order:
1. Explicit ``timeout_seconds`` argument (caller override).
2. ``BOB_FEATURE_TIMEOUT_SECONDS`` environment variable.
3. Default: 1800 s (30 minutes) — generous for large sub-agent runs, finite.

When a feature exceeds its wall-clock limit:
- A ``TIMEOUT`` telemetry event is emitted (WARNING-level log) with
  ``feature_id`` and elapsed seconds so chronic slow features are observable.
- :class:`FeatureTimeoutError` is raised so the orchestrator can classify the
  attempt as a timeout, reset the feature, and continue the loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Awaitable, TypeVar

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS: float = 1800.0  # 30 minutes

T = TypeVar("T")


class FeatureTimeoutError(RuntimeError):
    """Raised when a feature exceeds its wall-clock execution timeout."""

    def __init__(
        self,
        feature_id: str,
        elapsed_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self.feature_id = feature_id
        self.elapsed_seconds = elapsed_seconds
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Feature {feature_id} exceeded wall-clock timeout of "
            f"{timeout_seconds:.0f}s (elapsed: {elapsed_seconds:.1f}s)"
        )


def resolve_execution_timeout_seconds() -> float:
    """Return the per-feature wall-clock timeout in seconds.

    Reads ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment; falls back to
    :data:`_DEFAULT_TIMEOUT_SECONDS` (1800) on missing, empty, non-numeric, or
    non-positive values.  Always returns a positive float.
    """
    raw = os.environ.get("BOB_FEATURE_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %.0fs",
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return _DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        logger.warning(
            "Non-positive BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %.0fs",
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return _DEFAULT_TIMEOUT_SECONDS
    return value


def _emit_timeout_telemetry(
    feature_id: str,
    elapsed_seconds: float,
    timeout_seconds: float,
) -> None:
    """Emit a TIMEOUT telemetry event for observability of chronic slow features."""
    logger.warning(
        "TIMEOUT feature_id=%s elapsed_seconds=%.1f timeout_seconds=%.0f",
        feature_id,
        elapsed_seconds,
        timeout_seconds,
    )


async def enforce_feature_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard wall-clock timeout on a feature's execution coroutine.

    Wraps *coro* with ``asyncio.wait_for``.  When the coroutine exceeds the
    timeout, emits a ``TIMEOUT`` telemetry event and raises
    :class:`FeatureTimeoutError` so the orchestrator can:

    1. Classify the attempt as a timeout (charged or exempt retry).
    2. Reset the feature to ``'ready'`` and increment its attempt counter.
    3. Continue the loop so other features can progress.

    Args:
        feature_id: ID of the feature being executed.  Must be non-empty.
        coro: The awaitable representing the feature's sub-agent execution.
        timeout_seconds: Explicit override.  When ``None`` (default), reads
            ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment.  Must be a
            positive number when provided explicitly.

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty or *timeout_seconds* is
            explicitly provided as a non-positive value.
        FeatureTimeoutError: When *coro* exceeds the wall-clock timeout.
    """
    if not feature_id or not str(feature_id).strip():
        raise ValueError("feature_id must be a non-empty string")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(
            f"timeout_seconds must be positive when provided; got {timeout_seconds!r}"
        )

    effective_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else resolve_execution_timeout_seconds()
    )

    start = time.monotonic()
    try:
        return await asyncio.wait_for(
            asyncio.ensure_future(coro), timeout=effective_timeout
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        _emit_timeout_telemetry(feature_id, elapsed, effective_timeout)
        raise FeatureTimeoutError(feature_id, elapsed, effective_timeout)


__all__ = [
    "FeatureTimeoutError",
    "DEFAULT_FEATURE_TIMEOUT_SECONDS",
    "enforce_feature_timeout",
    "resolve_execution_timeout_seconds",
]

# Expose the default as a named constant for callers that need a reference value.
DEFAULT_FEATURE_TIMEOUT_SECONDS = _DEFAULT_TIMEOUT_SECONDS
