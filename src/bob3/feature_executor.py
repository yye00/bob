"""Per-feature hard wall-clock timeout enforcement (feature 86e81c64).

Provides :func:`enforce_timeout`, the canonical entry-point for ensuring a
single feature cannot hold an executing slot indefinitely.  The timeout is
configured via ``BOB3_FEATURE_TIMEOUT_SECONDS`` (default 1800 s / 30 min).

When a feature exceeds the timeout the caller MUST:
1. Terminate the sub-agent process tree.
2. Emit a TIMEOUT telemetry event with feature_id and elapsed seconds.
3. Reset the feature to 'ready' or increment its attempt count.
4. Continue the loop so other features can progress.

Integration: imported by bob3.orchestrator via
:func:`bob3.timeout.enforce_wall_clock_timeout` (which is the shared
implementation layer).  :func:`enforce_timeout` delegates to that shared
helper so the timeout resolution and telemetry are consistent across all
callers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, TypeVar

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 1800  # 30 minutes — generous but finite

T = TypeVar("T")


class FeatureTimeoutError(RuntimeError):
    """Raised when a feature exceeds its wall-clock timeout."""

    def __init__(self, feature_id: str, elapsed_seconds: float, timeout_seconds: float) -> None:
        self.feature_id = feature_id
        self.elapsed_seconds = elapsed_seconds
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Feature {feature_id} exceeded wall-clock timeout of "
            f"{timeout_seconds:.0f}s (elapsed: {elapsed_seconds:.1f}s)"
        )


def _read_timeout_from_env() -> float:
    """Read ``BOB3_FEATURE_TIMEOUT_SECONDS`` from the environment.

    Returns the configured timeout in seconds, falling back to
    ``_DEFAULT_TIMEOUT_SECONDS`` (1800) on any parse error or non-positive value.
    """
    raw = os.environ.get("BOB3_FEATURE_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_TIMEOUT_SECONDS)
    if value <= 0:
        logger.warning(
            "Non-positive BOB3_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_TIMEOUT_SECONDS)
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


async def enforce_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard wall-clock timeout on a feature execution coroutine.

    This is the primary public entry-point for per-feature execution timeout
    enforcement.  A feature that exceeds its timeout raises
    :class:`FeatureTimeoutError`; the caller is responsible for terminating the
    sub-agent process tree, emitting further observability events, resetting the
    feature's database state, and continuing the orchestration loop.

    Args:
        feature_id: ID of the feature being executed — included in the
            telemetry event and error message.  Must be a non-empty string.
        coro: The awaitable to run (e.g. the spawn_sub_agent call for this
            feature).
        timeout_seconds: Override the wall-clock timeout.  When ``None``
            (default), reads ``BOB3_FEATURE_TIMEOUT_SECONDS`` from the
            environment (falling back to 1800 s).

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty/blank or *timeout_seconds* is
            explicitly passed as a non-positive value.
        FeatureTimeoutError: When *coro* exceeds the wall-clock timeout.
    """
    if not feature_id or not str(feature_id).strip():
        raise ValueError("feature_id must be a non-empty string")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(
            f"timeout_seconds must be a positive number, got {timeout_seconds!r}"
        )

    effective_timeout = (
        timeout_seconds if timeout_seconds is not None else _read_timeout_from_env()
    )

    start = time.monotonic()
    try:
        return await asyncio.wait_for(asyncio.ensure_future(coro), timeout=effective_timeout)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        _emit_timeout_telemetry(feature_id, elapsed, effective_timeout)
        raise FeatureTimeoutError(feature_id, elapsed, effective_timeout)


__all__ = [
    "FeatureTimeoutError",
    "enforce_timeout",
]
