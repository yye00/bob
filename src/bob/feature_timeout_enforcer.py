"""Per-feature hard wall-clock timeout enforcer (feature 03cd988a).

Public entry-point for enforcing per-feature execution timeouts in the
bob orchestration loop. Wraps the underlying timeout machinery from
:mod:`bob.timeout` and exposes a stable, importable contract so callers
(orchestrator, tests) do not reach into run_loop internals.

The authoritative env var is ``BOB_FEATURE_TIMEOUT_SECONDS`` (default 1800 s).

When a feature exceeds its timeout the orchestrator MUST:
1. Terminate the sub-agent process tree.
2. Emit a TIMEOUT telemetry event (feature_id, elapsed seconds).
3. Reset the feature to 'ready' / increment its attempt count.
4. Continue the loop so other features can progress.
"""

from __future__ import annotations

import os
from typing import Awaitable, TypeVar

from bob.timeout import (  # noqa: F401 — re-exported for callers
    FeatureTimeoutError,
    FeatureTimeoutManager,
    enforce_wall_clock_timeout,
    resolve_timeout_seconds,
)

T = TypeVar("T")

DEFAULT_FEATURE_TIMEOUT_SECONDS: float = 1800.0


async def enforce_feature_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard wall-clock timeout on a single feature's coroutine.

    This is the canonical entry-point used by the orchestration loop. It
    wraps *coro* with ``asyncio.wait_for`` bounded by the effective timeout
    (explicit ``timeout_seconds`` or ``BOB_FEATURE_TIMEOUT_SECONDS``).

    Args:
        feature_id: Non-empty ID of the feature being executed. Included in
            the TIMEOUT telemetry event and error message.
        coro: The awaitable to run (e.g. the spawn_sub_agent call).
        timeout_seconds: Override timeout in seconds. When ``None`` (default),
            reads ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment,
            falling back to ``DEFAULT_FEATURE_TIMEOUT_SECONDS`` (1800 s).

    Returns:
        The result of *coro* when it completes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty/blank, or when *timeout_seconds*
            is explicitly passed as zero or negative.
        FeatureTimeoutError: When *coro* exceeds the wall-clock timeout. The
            caller MUST kill the sub-agent process tree, emit telemetry, and
            continue the loop.
    """
    if not feature_id or not feature_id.strip():
        raise ValueError("feature_id must be a non-empty string")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(
            f"timeout_seconds must be a positive number, got {timeout_seconds!r}"
        )
    return await enforce_wall_clock_timeout(
        feature_id, coro, timeout_seconds=timeout_seconds
    )


__all__ = [
    "DEFAULT_FEATURE_TIMEOUT_SECONDS",
    "FeatureTimeoutError",
    "FeatureTimeoutManager",
    "enforce_feature_timeout",
    "resolve_timeout_seconds",
]
