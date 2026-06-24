"""Per-feature wall-clock timeout enforcement for bob (feature eae370e2).

Provides :func:`enforce_wall_clock_timeout`, an async context manager and
helper that wraps a coroutine with ``asyncio.wait_for`` bounded by
``BOB_FEATURE_TIMEOUT_SECONDS`` (default 1800 s).

When a feature exceeds the timeout the caller MUST:
1. Terminate the sub-agent process tree.
2. Emit a TIMEOUT telemetry event with feature_id and elapsed seconds.
3. Reset the feature to 'ready' or increment its attempt count.
4. Continue the loop so other features can progress.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, TypeVar

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


def resolve_timeout_seconds() -> float:
    """Read ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment.

    Returns the configured timeout in seconds, falling back to
    ``_DEFAULT_TIMEOUT_SECONDS`` (1800) on any parse error or non-positive value.
    """
    raw = os.environ.get("BOB_FEATURE_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_TIMEOUT_SECONDS)
    if value <= 0:
        logger.warning(
            "Non-positive BOB_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_TIMEOUT_SECONDS)
    return value


def _emit_timeout_telemetry(feature_id: str, elapsed_seconds: float, timeout_seconds: float) -> None:
    """Emit a TIMEOUT telemetry event for observability of chronic slow features."""
    logger.warning(
        "TIMEOUT feature_id=%s elapsed_seconds=%.1f timeout_seconds=%.0f",
        feature_id,
        elapsed_seconds,
        timeout_seconds,
    )


async def enforce_wall_clock_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard wall-clock timeout on a feature coroutine.

    Wraps *coro* with ``asyncio.wait_for``.  If the coroutine exceeds the
    timeout, emits a TIMEOUT telemetry event and raises
    :class:`FeatureTimeoutError`.

    Args:
        feature_id: ID of the feature being executed — included in the
            telemetry event and error message.
        coro: The awaitable to run (e.g. the spawn_sub_agent call).
        timeout_seconds: Override the timeout.  When ``None`` (default),
            reads ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment.

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty or *timeout_seconds* is
            explicitly passed as a non-positive value (invalid input).
        FeatureTimeoutError: When *coro* exceeds the wall-clock timeout.
    """
    if not feature_id or not feature_id.strip():
        raise ValueError("feature_id must be a non-empty string")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(
            f"timeout_seconds must be positive, got {timeout_seconds!r}"
        )

    effective_timeout = timeout_seconds if timeout_seconds is not None else resolve_timeout_seconds()

    start = time.monotonic()
    try:
        return await asyncio.wait_for(asyncio.ensure_future(coro), timeout=effective_timeout)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        _emit_timeout_telemetry(feature_id, elapsed, effective_timeout)
        raise FeatureTimeoutError(feature_id, elapsed, effective_timeout)


async def enforce_feature_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard wall-clock timeout on a feature coroutine.

    Canonical public entry-point for per-feature execution timeout.
    Delegates to :func:`enforce_wall_clock_timeout`.

    Args:
        feature_id: ID of the feature being executed.
        coro: The awaitable to run.
        timeout_seconds: Override the timeout; reads
            ``BOB_FEATURE_TIMEOUT_SECONDS`` when ``None``.

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty or *timeout_seconds* is
            explicitly passed as a non-positive value.
        FeatureTimeoutError: When *coro* exceeds the wall-clock timeout.
    """
    return await enforce_wall_clock_timeout(
        feature_id, coro, timeout_seconds=timeout_seconds
    )


class FeatureTimeoutManager:
    """Context-manager wrapper that enforces a per-feature wall-clock timeout.

    Usage::

        async with FeatureTimeoutManager("feat-001", timeout_seconds=1800) as mgr:
            result = await mgr.run(some_coroutine())

    Raises :class:`FeatureTimeoutError` when the coroutine exceeds the timeout.
    Emits a TIMEOUT telemetry event (WARNING log) on expiry.
    """

    def __init__(
        self,
        feature_id: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        if not feature_id or not feature_id.strip():
            raise ValueError("feature_id must be a non-empty string")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds must be positive, got {timeout_seconds!r}"
            )
        self.feature_id = feature_id
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else resolve_timeout_seconds()
        )

    async def __aenter__(self) -> "FeatureTimeoutManager":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def run(self, coro: Awaitable[T]) -> T:
        """Run *coro* bounded by this manager's wall-clock timeout."""
        return await enforce_wall_clock_timeout(
            self.feature_id, coro, timeout_seconds=self.timeout_seconds
        )


__all__ = [
    "FeatureTimeoutError",
    "FeatureTimeoutManager",
    "enforce_feature_timeout",
    "enforce_wall_clock_timeout",
    "resolve_timeout_seconds",
]
