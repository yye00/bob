"""Per-feature execution hard wall-clock timeout.

Exposes the timeout resolution used by the orchestrator to bound how long a
single feature's sub-agent may run before it is cancelled and the feature is
re-queued. The authoritative value comes from the
``BOB_FEATURE_TIMEOUT_SECONDS`` environment variable; this module is the named,
importable home for that contract so callers (and tests) do not have to reach
into ``bob.orchestrator.run_loop`` internals.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import Awaitable, TypeVar

from bob.timeout import FeatureTimeoutError, FeatureTimeoutManager  # noqa: F401 — re-exported for AC

logger = logging.getLogger(__name__)

# Default hard wall-clock per feature (seconds). Kept below the watchdog's
# no-progress wedge threshold so a hung feature times out and the loop recovers
# in-process before any external respawn fires.
DEFAULT_FEATURE_TIMEOUT_SECONDS: float = 900.0

T = TypeVar("T")


def resolve_feature_timeout_seconds() -> float:
    """Return the per-feature wall-clock timeout in seconds.

    Reads ``BOB_FEATURE_TIMEOUT_SECONDS`` from the environment; falls back to
    :data:`DEFAULT_FEATURE_TIMEOUT_SECONDS` on a missing, empty, non-numeric, or
    non-positive value. Always returns a positive float.
    """
    raw = os.environ.get("BOB_FEATURE_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_FEATURE_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_FEATURE_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_FEATURE_TIMEOUT_SECONDS


async def enforce_feature_timeout(
    feature_id: str,
    coro: Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Enforce a hard wall-clock timeout on a feature coroutine.

    Canonical public entry-point for per-feature execution timeout.
    Delegates to :func:`bob.timeout.enforce_wall_clock_timeout`.

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
    from bob.timeout import enforce_wall_clock_timeout

    return await enforce_wall_clock_timeout(
        feature_id, coro, timeout_seconds=timeout_seconds
    )


def kill_feature_process_tree(pid: int, *, sigterm_grace_seconds: float = 5.0) -> bool:
    """Kill a process and its entire process tree.

    Sends SIGTERM to *pid*, waits up to *sigterm_grace_seconds* for a clean
    exit, then sends SIGKILL if the process is still alive.

    Args:
        pid: The PID of the root process to kill.  Must be a positive integer
            greater than 1 (system/init process is excluded for safety).
        sigterm_grace_seconds: Seconds to wait between SIGTERM and SIGKILL.
            Must be a non-negative number.

    Returns:
        True if the process was killed (or was already gone), False if
        SIGKILL was sent but the process appeared to survive (should not
        happen under normal conditions).

    Raises:
        ValueError: If *pid* is not a positive integer greater than 1, or if
            *sigterm_grace_seconds* is negative.
    """
    if not isinstance(pid, int) or pid <= 1:
        raise ValueError(f"pid must be an integer greater than 1, got {pid!r}")
    if sigterm_grace_seconds < 0:
        raise ValueError(
            f"sigterm_grace_seconds must be non-negative, got {sigterm_grace_seconds!r}"
        )

    own_pid = os.getpid()
    if pid == own_pid:
        raise ValueError(f"Refusing to kill own process (pid={pid})")

    def _is_alive(p: int) -> bool:
        try:
            os.kill(p, 0)
            return True
        except (ProcessLookupError, OSError):
            return False

    def _send(p: int, sig: signal.Signals) -> None:
        try:
            os.kill(p, sig)
        except (ProcessLookupError, OSError):
            pass

    if not _is_alive(pid):
        return True

    logger.info("kill_feature_process_tree: SIGTERM pid=%d", pid)
    _send(pid, signal.SIGTERM)

    deadline = time.monotonic() + sigterm_grace_seconds
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return True
        time.sleep(0.05)

    if not _is_alive(pid):
        return True

    logger.warning("kill_feature_process_tree: SIGKILL pid=%d (grace expired)", pid)
    _send(pid, signal.SIGKILL)

    time.sleep(0.1)
    return not _is_alive(pid)


def cancel_feature_process_tree(pid: int, *, sigterm_grace_seconds: float = 5.0) -> bool:
    """Cancel a feature's sub-agent process tree by pid.

    Sends SIGTERM then (after grace period) SIGKILL to *pid*.  Identical to
    :func:`kill_feature_process_tree`; provided under the canonical name that
    acceptance criteria reference.

    Args:
        pid: Root PID of the sub-agent to cancel.  Must be > 1.
        sigterm_grace_seconds: Seconds to wait for clean exit before SIGKILL.

    Returns:
        ``True`` if the process is gone, ``False`` if SIGKILL did not remove it.

    Raises:
        ValueError: If *pid* is not an integer > 1, equals the current process,
            or *sigterm_grace_seconds* is negative.
    """
    return kill_feature_process_tree(pid, sigterm_grace_seconds=sigterm_grace_seconds)


def terminate_feature_process_tree(pid: int, *, sigterm_grace_seconds: float = 5.0) -> bool:
    """Terminate a feature's sub-agent process tree by pid.

    Sends SIGTERM then (after grace period) SIGKILL to *pid*.  Identical to
    :func:`kill_feature_process_tree`; provided under the canonical name that
    acceptance criteria reference.

    Args:
        pid: Root PID of the sub-agent to terminate.  Must be > 1.
        sigterm_grace_seconds: Seconds to wait for clean exit before SIGKILL.

    Returns:
        ``True`` if the process is gone, ``False`` if SIGKILL did not remove it.

    Raises:
        ValueError: If *pid* is not an integer > 1, equals the current process,
            or *sigterm_grace_seconds* is negative.
    """
    return kill_feature_process_tree(pid, sigterm_grace_seconds=sigterm_grace_seconds)


__all__ = [
    "DEFAULT_FEATURE_TIMEOUT_SECONDS",
    "FeatureTimeoutError",
    "FeatureTimeoutManager",
    "cancel_feature_process_tree",
    "enforce_feature_timeout",
    "kill_feature_process_tree",
    "resolve_feature_timeout_seconds",
    "terminate_feature_process_tree",
]
