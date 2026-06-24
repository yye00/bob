"""Per-feature hard wall-clock execution timeout executor (feature 9bdba8e1).

Exposes :func:`execute_with_timeout` as the canonical entry-point for running
a feature's sub-agent coroutine with a hard wall-clock timeout.  A feature MUST
NEVER be able to hold an executing slot indefinitely — this module enforces
that guarantee with ``asyncio.wait_for``.

Timeout resolution order:
1. Explicit ``timeout_seconds`` argument (caller override).
2. ``BOB_FEATURE_TIMEOUT_SECONDS`` environment variable.
3. Default: 1800 s (30 minutes) — generous for large sub-agent runs, finite.

When a feature exceeds its wall-clock limit:
- A ``TIMEOUT`` telemetry event is emitted (WARNING-level log) with
  ``feature_id`` and elapsed seconds so chronic slow features are observable.
- :class:`FeatureExecutionTimeoutError` is raised so the orchestrator can
  classify the attempt as a timeout, reset the feature to 'ready', and
  continue the loop so other features can progress.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Awaitable, TypeVar

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS: float = 1800.0  # 30 minutes

T = TypeVar("T")


class FeatureExecutionTimeoutError(RuntimeError):
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


def resolve_timeout_seconds() -> float:
    """Return the per-feature wall-clock timeout in seconds.

    Reads ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment; falls back to
    :data:`DEFAULT_TIMEOUT_SECONDS` (1800) on missing, non-numeric, or
    non-positive values.
    """
    raw = os.environ.get("BOB_FEATURE_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %.0fs",
            raw,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        logger.warning(
            "Non-positive BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %.0fs",
            raw,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
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


async def execute_with_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Execute a feature coroutine with a hard wall-clock timeout.

    Wraps *coro* with ``asyncio.wait_for``.  When the coroutine exceeds the
    timeout, emits a ``TIMEOUT`` telemetry event (WARNING log with
    ``feature_id`` and elapsed seconds) and raises
    :class:`FeatureExecutionTimeoutError` so the orchestrator can:

    1. Cancel/kill the feature's sub-agent process tree.
    2. Classify the attempt as a timeout (charged or exempt retry).
    3. Reset the feature to ``'ready'`` or increment its attempt counter.
    4. Continue the loop so other features can progress.

    Args:
        feature_id: ID of the feature being executed.  Must be non-empty.
        coro: The awaitable representing the feature's sub-agent execution.
        timeout_seconds: Explicit override.  When ``None`` (default), reads
            ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment.  Must be
            positive when provided.

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty or *timeout_seconds* is
            explicitly provided as a non-positive value.
        FeatureExecutionTimeoutError: When *coro* exceeds the wall-clock
            timeout.
    """
    if not feature_id or not str(feature_id).strip():
        raise ValueError("feature_id must be a non-empty string")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(
            f"timeout_seconds must be positive when provided; got {timeout_seconds!r}"
        )

    effective_timeout = (
        timeout_seconds if timeout_seconds is not None else resolve_timeout_seconds()
    )

    start = time.monotonic()
    try:
        return await asyncio.wait_for(
            asyncio.ensure_future(coro), timeout=effective_timeout
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        _emit_timeout_telemetry(feature_id, elapsed, effective_timeout)
        raise FeatureExecutionTimeoutError(feature_id, elapsed, effective_timeout)


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "FeatureExecutionTimeoutError",
    "execute_with_timeout",
    "resolve_timeout_seconds",
]
