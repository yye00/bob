"""bb0c4b7a: Per-feature subagent cost cap — cost_control public API.

AC: File exists: src/bob3/cost_control.py
AC: Function defined: bob3.cost_control.enforce_per_attempt_cost_cap
AC: Function defined: bob3.cost_control.terminate_subagent_on_cap

This module is the canonical public entry point for per-feature-attempt cost
cap enforcement.  It delegates to the lower-level implementation in
``bob3.orchestrator.per_attempt_cost_cap``.

Background
----------
bob3 version 15 round 12 observed a pathological subagent burning $38.25 in
a single 5-minute attempt (total run cost spiked from $34.46 → $72.71).  The
outer ``bob3 run --max-cost`` flag caps TOTAL run cost but not per-feature
attempts.  This module closes that gap.

The cap defaults to $10 USD and is controlled by the
``BOB3_PER_ATTEMPT_COST_CAP`` environment variable (clamped to [0.5, 100]).

Integration
-----------
``bob3.orchestrator.run_loop`` calls :func:`enforce_per_attempt_cost_cap`
every 30 seconds while a subagent is in flight.  When the cap is exceeded,
SIGTERM is sent to the subagent, a 15-second grace period is allowed, then
SIGKILL is sent if the process is still alive.  The attempt is charged
(F-R7-561 lossless-cost: no free retry on cap-kill) and the audit log
records the sentinel ``subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>``.
"""

from __future__ import annotations

import logging

from bob3.orchestrator.per_attempt_cost_cap import (
    get_per_attempt_cap,
    should_terminate_subagent,
    terminate_subagent_on_cost_cap,
)

__all__ = [
    "enforce_per_attempt_cost_cap",
    "terminate_subagent_on_cap",
    "get_per_attempt_cap",
    "should_terminate_subagent",
]

logger = logging.getLogger(__name__)


def enforce_per_attempt_cost_cap(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> bool:
    """Check reported cost and terminate the subagent if the cap is exceeded.

    This is the single entry-point called by the orchestrator's cost-monitor
    loop.  It performs the full enforcement cycle:

    1. Check whether ``reported_cost`` exceeds the configured cap (via
       :func:`~bob3.orchestrator.per_attempt_cost_cap.should_terminate_subagent`).
    2. If the cap is exceeded, send SIGTERM → wait 15 s → SIGKILL (if still
       running), write the audit-log sentinel, and charge a refinement attempt
       (F-R7-561 lossless-cost: no free retry on cap-kill).
    3. Return ``True`` when the subagent was terminated, ``False`` otherwise.

    Parameters
    ----------
    feature_id:
        UUID string of the feature whose subagent is being monitored.
    pid:
        PID of the subagent process.  Passing PID ≤ 1 or the current
        process's own PID is a no-op (safety guard in the lower layer).
    reported_cost:
        Current USD cost of the in-flight subagent attempt as reported by
        the ``sub_agent_runs`` telemetry row.  Negative values are safe
        (treated as 0.0 — never trigger termination on bad telemetry).

    Returns
    -------
    bool
        ``True``  — cap was exceeded; subagent termination was initiated.
        ``False`` — cost is within the cap; subagent continues.

    Raises
    ------
    TypeError
        When ``reported_cost`` is a non-numeric type (e.g. dict, list, None).
    ValueError
        When ``reported_cost`` is a non-numeric string.
    """
    if not should_terminate_subagent(reported_cost):
        return False

    cap = get_per_attempt_cap()
    logger.warning(
        "cost_control.enforce_per_attempt_cost_cap: feature %s cost=%.4f exceeded "
        "cap=%.4f — initiating termination of PID %d",
        feature_id[:8],
        reported_cost,
        cap,
        pid,
    )

    terminate_subagent_on_cost_cap(
        feature_id=feature_id,
        pid=pid,
        reported_cost=reported_cost,
    )
    return True


def terminate_subagent_on_cap(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> None:
    """Terminate a cost-capped subagent and write the sentinel to the audit log.

    This is the canonical AC-required name for the termination step of cost
    cap enforcement.  It delegates to
    :func:`~bob3.orchestrator.per_attempt_cost_cap.terminate_subagent_on_cost_cap`.

    Steps:
    1. Send SIGTERM to ``pid``.
    2. Wait up to 15 s for the process to exit.
    3. Send SIGKILL if the process is still alive.
    4. Append sentinel ``subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>``
       to the feature audit log.
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
    terminate_subagent_on_cost_cap(
        feature_id=feature_id,
        pid=pid,
        reported_cost=reported_cost,
    )
