"""5d25f312: Zero-reported-cost MUST NOT disable budget enforcement.

When a sub-agent crashes mid-work, the stream-json parser may lose cost-delta
events, causing reported_cost==0 even though substantial work was done
(observable via work_events from progress.jsonl).

The dangerous code path interpreted cost==0 as "no budget to enforce" and
disabled the cap entirely. This module provides the canonical entry point the
orchestrator MUST call instead:

    :func:`enforce_minimum_cost_on_zero_report`

which implements the fix: cost==0 AND work_events > threshold → treat as
telemetry loss → apply per-feature ceiling AS IF the subagent had consumed
the full ceiling.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge per-feature ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash → charge 0.0 (F-R7-478 free retry).
* cost > 0 → normal case → returned as-is.

Threshold
---------
Default: 100 work events (env ``BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD``,
clamped to [1, 10000]).

Integration
-----------
This module is the top-level bob façade. It delegates to the lower-level
primitives in :mod:`bob.orchestrator.cost_telemetry_guard`. The orchestrator
``__init__.py`` must import :func:`enforce_minimum_cost_on_zero_report` to
satisfy the integration AC.
"""

from __future__ import annotations

import logging

from bob.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult,
    enforce_budget_on_zero_cost,
    is_cost_telemetry_lost,
    apply_pessimistic_cost,
    emit_cost_telemetry_lost_event,
    _read_threshold,
)

__all__ = [
    "enforce_minimum_cost_on_zero_report",
    "enforce_budget_on_zero_cost",
    "classify_cost_telemetry",
    "MinimumCostResult",
    "should_enforce_budget",
    "apply_zero_cost_safeguard",
]

#: Classification labels returned by :func:`classify_cost_telemetry`.
COST_TELEMETRY_NORMAL = "normal"
COST_TELEMETRY_LOST = "telemetry_lost"
COST_TELEMETRY_FREE_RETRY = "free_retry"

logger = logging.getLogger(__name__)


class MinimumCostResult:
    """Result returned by :func:`enforce_minimum_cost_on_zero_report`.

    Attributes
    ----------
    cost_to_charge:
        The cost to record against the budget. Equals ``per_feature_ceiling``
        when ``telemetry_lost`` is True (pessimistic enforcement applied);
        equals the SDK-reported cost otherwise (possibly 0.0 for a genuine
        free-retry spawn crash where no budget was consumed).
    telemetry_lost:
        True when cost==0 AND work_events > threshold — stream-json parser
        dropped cost-delta events during the crash, so the reported zero is
        not a true free run but a telemetry failure. Budget enforcement is
        applied via the per-feature ceiling in this case.
    """

    __slots__ = ("cost_to_charge", "telemetry_lost")

    def __init__(self, cost_to_charge: float, telemetry_lost: bool) -> None:
        self.cost_to_charge = float(cost_to_charge)
        self.telemetry_lost = bool(telemetry_lost)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"MinimumCostResult("
            f"cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def enforce_minimum_cost_on_zero_report(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> MinimumCostResult:
    """Enforce a minimum cost when zero-reported-cost may indicate telemetry loss.

    Implements the fix for the incident: feature 9b2e1060 crashed with
    work_events=176217 and reported_cost=0, causing the orchestrator to log
    "Cost is zero — budget enforcement disabled for this feature" and skip
    enforcement entirely. A zero cost combined with high work_events is a
    stream-json telemetry parse failure, not a free run. Calling this function
    instead of treating cost==0 as "no budget to enforce" prevents that failure
    mode.

    Parameters
    ----------
    reported_cost:
        The raw cost from the SDK (total_cost_usd). None is coerced to 0.0.
        Negative values are also treated as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
        Used to distinguish a genuine spawn-crash (work_events==0) from a
        telemetry-loss crash (work_events > threshold).
    per_feature_ceiling:
        Per-feature max-cost ceiling, applied pessimistically when telemetry
        is lost. Source: env ``BOB_PER_FEATURE_COST_CEILING``.
    feature_id:
        Feature UUID for structured logging of the ``cost_telemetry_lost`` event.
    exit_code:
        Sub-agent exit code (None if unknown). Included in the structured log.
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    MinimumCostResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN log, charge refinement attempt.
    - cost==0 AND work_events == 0 → genuine spawn crash → cost=0.0 (free retry
      via F-R7-478; budget enforcement remains active — no charge means no
      progress toward ceiling, which is correct).
    - cost > 0 → normal → returned as-is.
    - MUST NOT disable enforcement on zero-cost: this function always returns a
      result with enforcement applied when work was observed.
    """
    inner: EnforceBudgetResult = enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
    return MinimumCostResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )


def classify_cost_telemetry(
    reported_cost: float | None,
    work_events: int,
) -> str:
    """Classify a (reported_cost, work_events) pair into a telemetry verdict.

    This is the pure decision function underlying the enforcement path. It
    answers the question "what kind of zero-cost is this?" without applying
    any charge or emitting logs.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are treated
        as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl. Must be a
        non-negative integer.

    Returns
    -------
    str
        - ``COST_TELEMETRY_NORMAL`` (``"normal"``) — cost > 0; telemetry was
          delivered, no special handling required.
        - ``COST_TELEMETRY_LOST`` (``"telemetry_lost"``) — cost == 0 AND
          work_events > threshold; stream-json cost-delta events were dropped,
          so the reported zero is a telemetry miss. Budget enforcement MUST be
          applied via the per-feature ceiling.
        - ``COST_TELEMETRY_FREE_RETRY`` (``"free_retry"``) — cost == 0 AND
          work_events <= threshold; a genuine spawn-crash with little/no work,
          eligible for the F-R7-478 free-retry path.

    Raises
    ------
    ValueError
        If ``work_events`` is not an int, is a bool, or is negative — invalid
        input must not silently succeed.
    """
    if isinstance(work_events, bool) or not isinstance(work_events, int):
        raise ValueError(
            f"work_events must be a non-negative int, got {work_events!r}"
        )
    if work_events < 0:
        raise ValueError(
            f"work_events must be non-negative, got {work_events!r}"
        )

    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0
    if cost > 0.0:
        return COST_TELEMETRY_NORMAL
    if work_events > _read_threshold():
        return COST_TELEMETRY_LOST
    return COST_TELEMETRY_FREE_RETRY


def should_enforce_budget(
    reported_cost: float | None,
    work_events: int,
) -> bool:
    """Return True when budget enforcement MUST proceed, regardless of reported cost.

    Core invariant: zero-reported-cost MUST NOT disable budget enforcement.

    Budget enforcement is always required except for a genuine spawn-crash with
    zero work (work_events == 0 AND cost == 0), the F-R7-478 free-retry path
    where no budget was consumed.

    When reported_cost is zero (or None/negative) AND work_events > threshold,
    the cost is ambiguous (stream-json parser may have dropped cost-delta events).
    Enforcement is still required — the caller should apply the pessimistic ceiling.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are treated as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.

    Returns
    -------
    bool
        True  — budget enforcement MUST proceed.
        False — ONLY for genuine spawn-crash free-retry: cost==0 AND work_events==0.
    """
    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0
    if cost > 0.0:
        return True
    return work_events > 0 or is_cost_telemetry_lost(
        reported_cost=reported_cost, work_events=work_events
    )


def apply_zero_cost_safeguard(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> MinimumCostResult:
    """Apply the zero-cost safeguard: enforce budget when reported cost is zero.

    When reported_cost is zero (or None/negative) AND work_events exceed the
    telemetry-loss threshold, this function treats the zero as a stream-json
    telemetry miss and applies the per-feature ceiling as a pessimistic charge.
    This is the safeguard that prevents zero-reported-cost from disabling budget
    enforcement under crash conditions.

    Delegates to :func:`enforce_minimum_cost_on_zero_report`.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied pessimistically when telemetry is lost.
    feature_id:
        Feature UUID for structured logging of the cost_telemetry_lost event.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    MinimumCostResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.
    """
    return enforce_minimum_cost_on_zero_report(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
