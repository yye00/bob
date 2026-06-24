"""Per-feature wall-clock timeout enforcement for the orchestrator (b801d6a7).

Provides two public functions required by the acceptance criteria:

* :func:`enforce_feature_timeout` — wraps a coroutine with a hard wall-clock
  deadline using ``asyncio.wait_for``, emits a TIMEOUT telemetry event on
  expiry, and raises :class:`bob.timeout.FeatureTimeoutError`.

* :func:`classify_timeout_attempt` — decides whether a timed-out attempt
  should be charged as a real retry or granted an exempt retry, mirroring
  the startup-crash-exempt logic used elsewhere in the orchestrator.

Environment variable
--------------------
``BOB_FEATURE_TIMEOUT_SECONDS`` (float, seconds) — configures the hard
wall-clock deadline per feature attempt.  Defaults to 1800 (30 minutes),
which is generous enough for large sub-agent runs while remaining finite.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Any, Awaitable, Literal, TypeVar

from bob.timeout import (
    FeatureTimeoutError,
    enforce_wall_clock_timeout,
    resolve_timeout_seconds,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Sentinel directory written by the startup-crash-exempt feature.
_STARTUP_EXEMPT_DIR = ".bob_startup_exempt"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enforce_feature_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard per-feature wall-clock timeout on *coro*.

    Delegates to :func:`bob.timeout.enforce_wall_clock_timeout`, which wraps
    *coro* with ``asyncio.wait_for`` and raises :class:`FeatureTimeoutError`
    on expiry after emitting a TIMEOUT telemetry log line.

    The orchestrator MUST call this instead of awaiting spawn_sub_agent
    directly so that a wedged feature can never hold an executing slot
    indefinitely.  On :class:`FeatureTimeoutError`:

    1. Terminate the sub-agent process tree (caller responsibility).
    2. Call :func:`classify_timeout_attempt` to decide retry-charge policy.
    3. Reset the feature to ``ready`` or ``needs_human`` and continue the loop.

    Args:
        feature_id: UUID of the feature being executed; included in the
            telemetry event and error message.
        coro: Awaitable to run (typically the spawn_sub_agent call).
        timeout_seconds: Hard deadline in seconds.  When ``None``, reads
            ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment (default
            1800 s).

    Returns:
        The result of *coro* when it finishes within the timeout.

    Raises:
        ValueError: When *feature_id* is empty or *timeout_seconds* is
            explicitly non-positive.
        FeatureTimeoutError: When *coro* exceeds the wall-clock deadline.
    """
    return await enforce_wall_clock_timeout(
        feature_id,
        coro,
        timeout_seconds=timeout_seconds,
    )


def classify_timeout_attempt(
    feature_id: str,
    *,
    workspace: str | None = None,
    elapsed_seconds: float = 0.0,
) -> Literal["charged", "exempt"]:
    """Classify a timed-out attempt as either charged or exempt from retry budget.

    Mirrors the startup-crash-exempt logic used by the orchestrator for
    MCP-transport crashes: if the sub-agent produced no on-disk artifact
    during the attempt (evidence that it hung immediately without doing
    meaningful work), the timeout is classified as ``"exempt"`` — the
    attempt is NOT charged against the feature's refinement budget.  If the
    sub-agent persisted any work before timing out the attempt is
    ``"charged"`` so that a spec whose implementation always hangs at the
    same point cannot loop for free.

    The startup-exempt sentinel is stored in ``<workspace>/.bob_startup_exempt/``
    (one ``.count`` file per feature, written by the orchestrator's crash
    handler).  When the sentinel is present the timeout is considered
    ``"charged"`` because the feature did do real work.  When the sentinel is
    absent the timeout is classified as ``"exempt"``.

    Args:
        feature_id: UUID of the feature that timed out.
        workspace: Path to the project workspace root.  Defaults to the
            current working directory when ``None``.
        elapsed_seconds: Wall-clock seconds elapsed before the timeout fired,
            used for observability logging only.

    Returns:
        ``"charged"``  — increment refinement_attempts; no free retry.
        ``"exempt"``   — do NOT increment refinement_attempts; grant free retry.

    Raises:
        ValueError: When *feature_id* is empty.
    """
    if not feature_id or not feature_id.strip():
        raise ValueError("feature_id must be a non-empty string")

    ws = pathlib.Path(workspace) if workspace else pathlib.Path.cwd()
    sentinel_path = ws / _STARTUP_EXEMPT_DIR / f"{feature_id}.count"

    # If the startup-exempt sentinel exists, the sub-agent started doing real
    # work — charge the attempt.
    artifact_persisted = sentinel_path.exists()

    # Also check for any python source or test files that may have been
    # written during the (partial) attempt.  A timed-out run that produced
    # source artifacts should be charged.
    src_dir = ws / "src"
    if not artifact_persisted and src_dir.is_dir():
        try:
            for candidate in (ws / "tests").glob("*.py"):
                if feature_id[:8].lower() in candidate.name.lower():
                    artifact_persisted = True
                    break
        except Exception:
            pass

    classification: Literal["charged", "exempt"] = "charged" if artifact_persisted else "exempt"

    logger.warning(
        "classify_timeout_attempt: feature=%s elapsed=%.1fs artifact_persisted=%s "
        "-> classification=%s",
        feature_id[:8],
        elapsed_seconds,
        artifact_persisted,
        classification,
    )
    return classification


__all__ = [
    "FeatureTimeoutError",
    "classify_timeout_attempt",
    "enforce_feature_timeout",
    "resolve_timeout_seconds",
]
