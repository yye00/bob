"""754a4bf4: Zero-reported-cost MUST NOT disable budget enforcement.

Context
-------
Feature 9b2e1060 crashed with work_events=176217, exit_code=1, cost_usd=0.
The orchestrator logged "Cost is zero — budget enforcement disabled for this
feature." A zero cost combined with 176K work events is a stream-json parser
failure, not a free run. The enforcement path interpreted cost==0 as "no
budget to enforce" and turned OFF the cap — enabling unbounded subagent burn.

This module provides the canonical entry point:

    :func:`enforce_cost_floor_on_zero_report`

which the orchestrator MUST call instead of silently skipping budget
enforcement when reported cost is zero.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash → cost=0.0 (free retry).
* cost > 0 → normal case → returned as-is.

The ``cost_telemetry_lost`` structured event is emitted (as a WARN log)
whenever the pessimistic ceiling is applied, with all fields required for
operator triage: (feature_id, work_events, exit_code, attempt).

Threshold
---------
Default: 100 work events (env BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD,
clamped to [1, 10000]).

Relationship to existing modules
---------------------------------
This module delegates detection and application to the lower-level primitives
in :mod:`bob3.orchestrator.cost_telemetry_guard`.  The orchestrator's
``__init__.py`` exposes ``enforce_cost_floor_on_zero_report`` to satisfy the
integration AC.
"""

from __future__ import annotations

from bob3.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult,
    enforce_budget_on_zero_cost,
)

__all__ = [
    "enforce_cost_floor_on_zero_report",
    "CostFloorResult",
]


class CostFloorResult:
    """Result returned by :func:`enforce_cost_floor_on_zero_report`.

    Attributes
    ----------
    cost_to_charge:
        The cost to record and charge against the budget.
        Equals ``per_feature_ceiling`` when ``telemetry_lost`` is True;
        equals the SDK-reported cost otherwise (possibly 0.0 for a
        genuine free-retry spawn crash).
    telemetry_lost:
        True when cost==0 AND work_events > threshold (stream-json miss
        requiring pessimistic charge). False for normal or free-retry cases.
    """

    __slots__ = ("cost_to_charge", "telemetry_lost")

    def __init__(self, cost_to_charge: float, telemetry_lost: bool) -> None:
        self.cost_to_charge = float(cost_to_charge)
        self.telemetry_lost = bool(telemetry_lost)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CostFloorResult("
            f"cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def enforce_cost_floor_on_zero_report(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostFloorResult:
    """Enforce budget floor when reported cost is zero and work was observed.

    This function MUST be called by the orchestrator whenever reported_cost==0
    after a sub-agent run. It enforces the invariant that zero-cost NEVER
    disables budget enforcement when substantial work was performed.

    When cost==0 AND work_events > threshold, the function treats cost as
    UNKNOWN-but-nonzero (stream-json telemetry miss) and applies the per-feature
    ceiling as a pessimistic charge. A structured ``cost_telemetry_lost`` WARN
    event is emitted with (feature_id, work_events, exit_code, attempt).

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None is coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied as a pessimistic charge when
        telemetry is lost (env BOB3_PER_FEATURE_COST_CEILING).
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    CostFloorResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0. Budget enforcement cannot
        operate without a positive ceiling.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN event.
    - cost==0 AND work_events == 0 → genuine spawn crash → cost=0.0 (free retry;
      budget enforcement remains active — no budget was consumed).
    - cost > 0 → normal → returned as-is.
    """
    if per_feature_ceiling <= 0:
        raise ValueError(
            f"enforce_cost_floor_on_zero_report: per_feature_ceiling must be positive, "
            f"got {per_feature_ceiling!r}. Budget enforcement requires a positive ceiling."
        )

    inner: EnforceBudgetResult = enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
    return CostFloorResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )
