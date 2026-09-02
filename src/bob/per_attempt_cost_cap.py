"""29bde5f2: Per-feature subagent cost cap — public module (default $10).

Problem
-------
bob version 15 round 12 observed a pathological subagent burning $38.25 in
a single 5-minute attempt (cost spiked $34.46 → $72.71). The outer
``bob run --max-cost`` flag caps TOTAL run cost but NOT per-feature attempts.
A runaway subagent can consume tens of dollars on a single attempt before the
total run-cost cap or the attempts cap fires.

Solution
--------
This module provides the canonical ``enforce_per_attempt_cost_cap`` function.
The orchestrator's cost-monitor task calls this function every 30 s while a
subagent is in flight. If the reported cost exceeds the configured cap the
subagent is terminated (SIGTERM → 15 s grace → SIGKILL), the attempt is
charged (F-R7-561 lossless-cost: no free retry), and the audit log records
the sentinel ``subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>``.

Default cap: $10 USD. Override via ``BOB_PER_ATTEMPT_COST_CAP`` (clamped
to [0.5, 100]).
"""

from __future__ import annotations

from bob.cost_cap import enforce_per_attempt_cost_cap  # noqa: F401 — re-export
from bob.orchestrator.per_attempt_cost_cap import (
    get_per_attempt_cap,
    terminate_subagent_on_cost_cap,
)

__all__ = [
    "enforce_attempt_cost_cap",
    "enforce_cost_cap",
    "enforce_per_attempt_cost_cap",
    "resolve_cost_cap",
    "send_sigterm_on_cost_exceeded",
]


def resolve_cost_cap() -> float | None:
    """Resolve the effective per-attempt cost cap in USD.

    Reads ``BOB_PER_ATTEMPT_COST_CAP`` (default 10.0), clamps it to the valid
    range [0.5, 100], and returns the result. ``unlimited``/``none`` returns
    ``None``; malformed configuration raises so it cannot silently disable the
    guard. Canonical public name for the cap-resolution step required by the
    feature's acceptance criteria.

    Returns
    -------
    float | None
        The per-attempt cap in USD, or ``None`` for explicit unlimited mode.
    """
    return get_per_attempt_cap()


def enforce_attempt_cost_cap(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> bool:
    """Enforce the per-attempt cost cap for an in-flight subagent.

    If ``reported_cost`` exceeds the cap resolved by :func:`resolve_cost_cap`,
    the subagent (``pid``) is terminated (SIGTERM → 15 s grace → SIGKILL), the
    attempt is charged per F-R7-561 lossless-cost rules, and the audit sentinel
    ``subagent_killed_on_attempt_cost_cap=<feature_id>:<cost>`` is written.
    Otherwise this is a no-op.

    Canonical public name required by the feature's acceptance criteria;
    delegates to the verified :func:`enforce_per_attempt_cost_cap`.

    Returns
    -------
    bool
        True when the subagent was terminated, False otherwise.
    """
    return enforce_per_attempt_cost_cap(
        feature_id=feature_id,
        pid=pid,
        reported_cost=reported_cost,
    )


def enforce_cost_cap(
    *,
    feature_id: str,
    pid: int,
    reported_cost: float,
) -> bool:
    """Check reported cost and enforce the per-attempt cap.

    Alias for ``enforce_per_attempt_cost_cap`` satisfying the AC requirement
    for ``bob.per_attempt_cost_cap.enforce_cost_cap``.

    Returns True when the subagent was terminated, False otherwise.
    """
    return enforce_per_attempt_cost_cap(
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
    """Send SIGTERM (then SIGKILL after 15 s grace) when cost exceeds cap.

    Delegates to ``bob.orchestrator.per_attempt_cost_cap.terminate_subagent_on_cost_cap``.
    Satisfies the AC requirement for
    ``bob.per_attempt_cost_cap.send_sigterm_on_cost_exceeded``.
    """
    terminate_subagent_on_cost_cap(
        feature_id=feature_id,
        pid=pid,
        reported_cost=reported_cost,
    )
