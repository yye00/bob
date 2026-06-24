"""27eaa1de: Per-feature subagent cost cap for the orchestration loop.

Context
-------
bob3 version 15 round 12 observed a pathological subagent burning $38.25
in a single 5-minute attempt (cost spiked from $34.46 → $72.71).  The
outer ``bob3 run --max-cost`` flag caps TOTAL run cost but not per-feature
attempts, so a runaway subagent could consume 3-4× the median feature cost
before any guard fired.

This module provides three functions called by run_loop periodically (every
30 s) while a subagent is in flight:

1. :func:`get_per_attempt_cap` — reads / clamps the configured cap.
2. :func:`should_terminate_subagent` — returns True when reported cost
   has crossed the cap.
3. :func:`terminate_subagent_on_cost_cap` — sends SIGTERM, waits 15 s,
   sends SIGKILL if the process is still alive, writes the sentinel to the
   feature audit log, and charges a refinement attempt per F-R7-561
   lossless-cost rules.

Environment variable
--------------------
``BOB3_PER_ATTEMPT_COST_CAP`` (float, USD) — overrides the default 10.0.
Clamped to [0.5, 100].  Values outside the range are silently clamped (not
rejected) so operators can safely set ``0`` (→ 0.5) or ``9999`` (→ 100)
without crashing the orchestrator.

Lossless-cost invariant (F-R7-561)
-----------------------------------
Terminating a subagent mid-attempt still counts as a real attempt:
``increment_refinement_attempts`` is called so the attempt is charged and
the feature transitions back to ``ready`` (or ``needs_human`` when the
attempts cap is exhausted).  We do NOT grant a free retry.
"""

from __future__ import annotations

import logging
import os
import signal
import time

from bob3 import db

logger = logging.getLogger(__name__)

_DEFAULT_CAP = 10.0
_MIN_CAP = 0.5
_MAX_CAP = 100.0

_SIGTERM_GRACE_SECONDS = 15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_per_attempt_cap() -> float:
    """Return the per-attempt cost cap in USD.

    Reads ``BOB3_PER_ATTEMPT_COST_CAP`` from the environment, applies
    [0.5, 100] clamping, and returns the result.  Returns 10.0 when the
    variable is unset or not a valid float.

    Returns
    -------
    float
        Per-attempt cap in USD, always in [0.5, 100].
    """
    raw = os.environ.get("BOB3_PER_ATTEMPT_COST_CAP", "").strip()
    if raw:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return _DEFAULT_CAP
        return max(_MIN_CAP, min(_MAX_CAP, value))
    return _DEFAULT_CAP


def should_terminate_subagent(reported_attempt_cost: float) -> bool:
    """Return True when ``reported_attempt_cost`` exceeds the configured cap.

    Parameters
    ----------
    reported_attempt_cost:
        Current cost of the in-flight subagent attempt in USD.  Negative
        values are treated as 0.0 (safe default — never trigger termination
        on bad telemetry).

    Returns
    -------
    bool
        True  — cost > cap; terminate the subagent.
        False — cost ≤ cap; let it continue.
    """
    cost = max(0.0, float(reported_attempt_cost))
    cap = get_per_attempt_cap()
    return cost > cap


def terminate_subagent_on_cost_cap(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> None:
    """Terminate a cost-capped subagent and write the sentinel to the audit log.

    Steps:
    1. Send SIGTERM to ``pid``.
    2. Wait up to 15 s for the process to exit.
    3. Send SIGKILL if the process is still alive.
    4. Append sentinel ``subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>``
       to the feature audit log via ``db.create_evidence``.
    5. Call ``db.increment_refinement_attempts`` so the attempt is charged
       (F-R7-561 lossless-cost: no free retry on cap-kill).

    Parameters
    ----------
    feature_id:
        UUID string of the feature whose subagent is being terminated.
    pid:
        PID of the subagent process.  The function is a no-op when
        ``pid <= 1`` or ``pid == os.getpid()`` (safety guard).
    reported_cost:
        The cost that triggered the termination (for audit log).
    """
    own_pid = os.getpid()
    if pid <= 1 or pid == own_pid:
        logger.warning(
            "terminate_subagent_on_cost_cap: refusing to signal PID %d "
            "(safety: own pid or system pid) for feature %s",
            pid,
            feature_id[:8],
        )
        return

    cap = get_per_attempt_cap()
    logger.warning(
        "per_attempt_cost_cap: feature %s cost=%.4f exceeded cap=%.4f; "
        "sending SIGTERM to PID %d",
        feature_id[:8],
        reported_cost,
        cap,
        pid,
    )

    _send_signal(pid, signal.SIGTERM)

    exited = _wait_for_exit(pid, _SIGTERM_GRACE_SECONDS)
    if not exited:
        logger.warning(
            "per_attempt_cost_cap: PID %d did not exit after %ds grace; "
            "sending SIGKILL for feature %s",
            pid,
            _SIGTERM_GRACE_SECONDS,
            feature_id[:8],
        )
        _send_signal(pid, signal.SIGKILL)

    # Write sentinel to feature audit log.
    sentinel = f"subagent_killed_on_attempt_cost_cap={feature_id}:{reported_cost:.4f}"
    try:
        import json as _json
        db.create_evidence(
            feature_id=feature_id,
            type="attempt_cost_cap_kill",
            content=_json.dumps({
                "sentinel": sentinel,
                "feature_id": feature_id,
                "reported_cost": reported_cost,
                "cap": cap,
                "pid": pid,
            }),
        )
    except Exception:
        pass  # audit log is best-effort; never crash the orchestrator
    logger.info("SENTINEL %s", sentinel)

    # Charge a refinement attempt (F-R7-561 lossless-cost: no free retry).
    try:
        db.increment_refinement_attempts(feature_id)
    except Exception:
        logger.warning(
            "per_attempt_cost_cap: failed to increment refinement_attempts "
            "for feature %s; attempt may not be properly charged",
            feature_id[:8],
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _send_signal(pid: int, sig: signal.Signals) -> None:
    """Send ``sig`` to ``pid``, ignoring ProcessLookupError."""
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        logger.warning("Permission denied sending %s to PID %d", sig.name, pid)


def _pid_is_alive(pid: int) -> bool:
    """Return True if ``pid`` is still alive (signal-0 probe)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we can't signal it


def _wait_for_exit(pid: int, timeout_s: float) -> bool:
    """Poll until ``pid`` exits or ``timeout_s`` elapses.

    Returns True if the process exited within the window.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_is_alive(pid):
            return True
        time.sleep(0.25)
    return not _pid_is_alive(pid)
