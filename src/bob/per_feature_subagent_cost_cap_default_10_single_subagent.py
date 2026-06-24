"""b920dbfb: Per-feature subagent cost cap facade (default $10).

Problem
-------
bob version 15 round 12 observed a pathological subagent burning $38.25 in
a single 5-minute attempt (cost spiked $34.46 → $72.71). The outer
``bob run --max-cost`` flag caps TOTAL run cost but NOT per-feature attempts.
A runaway subagent can consume tens of dollars on a single attempt before the
total run-cost cap or the attempts cap fires.

Solution
--------
This module is the public facade for the per-feature-attempt cost cap.  The
orchestrator's cost-monitor task calls
:func:`per_feature_subagent_cost_cap_default_10_single_subagent` every 30 s
while a subagent is in flight.  If the reported cost exceeds the configured
cap the subagent is terminated (SIGTERM → 15 s grace → SIGKILL), the attempt
is charged (F-R7-561 lossless-cost: no free retry), and the audit log records
the sentinel ``subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>``.

Default cap: $10 USD.  Override via ``BOB_PER_ATTEMPT_COST_CAP`` (clamped
to [0.5, 100]).

The lower-level signal delivery, audit-log writing, and attempt charging are
handled by ``bob.orchestrator.per_attempt_cost_cap`` and surfaced through
``bob.cost_cap.enforce_per_attempt_cap``.
"""

from __future__ import annotations

import logging

from bob.cost_cap import enforce_per_attempt_cap

__all__ = [
    "DEFAULT_CAP",
    "per_feature_subagent_cost_cap_default_10_single_subagent",
]

logger = logging.getLogger(__name__)

DEFAULT_CAP: float = 10.0


def per_feature_subagent_cost_cap_default_10_single_subagent(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> bool:
    """Check reported cost and terminate the subagent if the per-attempt cap is exceeded.

    This is the canonical entry point for the per-feature subagent cost cap
    (feature b920dbfb). It delegates to
    :func:`bob.cost_cap.enforce_per_attempt_cap`, which in turn delegates to
    ``bob.orchestrator.per_attempt_cost_cap`` for signal delivery and audit
    logging.

    The cap defaults to $10 USD and is controlled by the environment variable
    ``BOB_PER_ATTEMPT_COST_CAP`` (clamped to [0.5, 100]).

    Parameters
    ----------
    feature_id:
        UUID string of the feature whose subagent is being monitored.
    pid:
        PID of the subagent process. Passing PID ≤ 1 or the current
        process's own PID is a no-op (safety guard in the lower layer).
    reported_cost:
        Current USD cost of the in-flight subagent attempt as reported by
        the ``sub_agent_runs`` telemetry row. Negative values are safe
        (treated as 0.0 — never trigger termination on bad telemetry).

    Returns
    -------
    bool
        ``True``  — cap was exceeded; subagent termination was initiated.
        ``False`` — cost is within the cap; subagent continues.
    """
    return enforce_per_attempt_cap(
        feature_id=feature_id,
        pid=pid,
        reported_cost=reported_cost,
    )
