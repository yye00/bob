"""e93f7fc4: Per-feature subagent cost cap — public facade.

This module provides the high-level ``enforce_per_attempt_cap`` function used
by the orchestrator to check and enforce the per-feature-attempt cost ceiling.

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
``bob3.orchestrator.run_loop`` calls :func:`enforce_per_attempt_cap` in the
background cost-monitor task every 30 seconds while a subagent is in flight.
The lower-level signal delivery and audit-log sentinel are handled by
``bob3.orchestrator.per_attempt_cost_cap``.
"""

from __future__ import annotations

import logging

from bob3.orchestrator.per_attempt_cost_cap import (
    get_per_attempt_cap,
    should_terminate_subagent,
    terminate_subagent_on_cost_cap,
)
from bob3.per_project_cost_cap_must_env_overridable_default import (
    resolve_max_cost_usd,
)

__all__ = [
    "enforce_per_attempt_cost_cap",
    "enforce_per_attempt_cap",
    "get_cost_cap_from_env",
    "get_cost_cap_limit",
    "get_cost_cap_threshold",
    "get_per_attempt_cap",
    "parse_cost_cap_config",
    "resolve_max_cost_usd",
    "send_sigterm_on_cost_exceeded",
    "should_terminate_subagent",
]

logger = logging.getLogger(__name__)


def get_cost_cap_from_env() -> float:
    """Return the per-attempt cost cap by reading BOB3_PER_ATTEMPT_COST_CAP.

    Reads ``BOB3_PER_ATTEMPT_COST_CAP`` from the environment, clamps the
    result to [0.5, 100], and returns 10.0 USD when unset or invalid.

    Returns
    -------
    float
        Per-attempt cost cap in USD, always in [0.5, 100].
    """
    return get_per_attempt_cap()


def get_cost_cap_limit() -> float:
    """Return the current per-attempt cost cap limit in USD.

    Reads ``BOB3_PER_ATTEMPT_COST_CAP`` from the environment and returns the
    configured cap, clamped to [0.5, 100].  Defaults to 10.0 USD.

    This is the canonical name for the AC ``Function defined:
    bob3.cost_cap.get_cost_cap_limit``; it delegates to
    :func:`~bob3.orchestrator.per_attempt_cost_cap.get_per_attempt_cap`.

    Returns
    -------
    float
        Per-attempt cost cap in USD, always in [0.5, 100].
    """
    return get_per_attempt_cap()


def get_cost_cap_threshold() -> float:
    """Return the current per-attempt cost cap threshold in USD.

    Reads ``BOB3_PER_ATTEMPT_COST_CAP`` from the environment and returns the
    configured cap, clamped to [0.5, 100].  Defaults to 10.0 USD.

    This is the AC-required canonical name ``bob3.cost_cap.get_cost_cap_threshold``.
    It delegates to
    :func:`~bob3.orchestrator.per_attempt_cost_cap.get_per_attempt_cap`.

    Returns
    -------
    float
        Per-attempt cost cap in USD, always in [0.5, 100].
    """
    return get_per_attempt_cap()


def parse_cost_cap_config(env_value: str | None = None) -> float:
    """Parse and validate a cost cap configuration value.

    Accepts a raw string (e.g. from an environment variable), converts it to
    float, and clamps the result to [0.5, 100].  Returns the default 10.0
    when ``env_value`` is None, empty, or not a valid float.

    Parameters
    ----------
    env_value:
        Raw string value to parse, or None to use the default.

    Returns
    -------
    float
        Validated cap in USD, always in [0.5, 100].

    Raises
    ------
    ValueError
        When ``env_value`` is a non-string, non-None type (e.g. a dict or list)
        that cannot be processed.
    """
    _DEFAULT = 10.0
    _MIN = 0.5
    _MAX = 100.0

    if env_value is None:
        return _DEFAULT
    if not isinstance(env_value, str):
        raise ValueError(
            f"parse_cost_cap_config: expected str or None, got {type(env_value).__name__!r}"
        )
    stripped = env_value.strip()
    if not stripped:
        return _DEFAULT
    try:
        value = float(stripped)
    except (TypeError, ValueError):
        return _DEFAULT
    return max(_MIN, min(_MAX, value))


def enforce_per_attempt_cap(
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
    """
    if not should_terminate_subagent(reported_cost):
        return False

    cap = get_per_attempt_cap()
    logger.warning(
        "cost_cap.enforce_per_attempt_cap: feature %s cost=%.4f exceeded "
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


def enforce_per_attempt_cost_cap(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> bool:
    """Canonical AC name for :func:`enforce_per_attempt_cap`.

    Delegates entirely to :func:`enforce_per_attempt_cap`.  The AC specifies
    the name ``bob3.cost_cap.enforce_per_attempt_cost_cap``; this wrapper
    ensures the function can be found by static analysis tools that require
    a ``def`` statement.
    """
    return enforce_per_attempt_cap(
        feature_id=feature_id,
        pid=pid,
        reported_cost=reported_cost,
    )


def send_sigterm_on_cost_exceeded(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> None:
    """Send SIGTERM to a subagent whose reported cost exceeds the configured cap.

    This is the AC-required public name for the signal-delivery step of cost
    cap enforcement.  It checks whether ``reported_cost`` exceeds the cap
    (``BOB3_PER_ATTEMPT_COST_CAP``, default 10.0 USD) and, if so, delegates
    to :func:`~bob3.orchestrator.per_attempt_cost_cap.terminate_subagent_on_cost_cap`
    which sends SIGTERM → waits 15 s → SIGKILL if still alive → writes the
    audit sentinel → charges the refinement attempt.

    When ``reported_cost`` is within the cap this function is a no-op.

    Parameters
    ----------
    feature_id:
        UUID string of the feature whose subagent is being monitored.
    pid:
        PID of the subagent process.  PID ≤ 1 or the calling process's own
        PID are safety-rejected in the lower layer.
    reported_cost:
        Current USD cost of the in-flight subagent attempt.  Negative values
        are safe (treated as 0.0 — never trigger termination on bad telemetry).
    """
    if not should_terminate_subagent(reported_cost):
        return

    cap = get_per_attempt_cap()
    logger.warning(
        "cost_cap.send_sigterm_on_cost_exceeded: feature %s cost=%.4f exceeded "
        "cap=%.4f — sending SIGTERM to PID %d",
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
