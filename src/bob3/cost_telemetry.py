"""789ac06d: Zero-reported-cost MUST NOT disable budget enforcement.

Context
-------
bob3 v.15 r12 observed feature 9b2e1060 crash with work_events=176217,
exit_code=1, cost_usd=0.  The orchestrator logged "Cost is zero —
budget enforcement disabled for this feature."  A zero cost combined with
176K work events is a stream-json parser failure, not a free run.  Yet the
enforcement path interpreted cost==0 as "no budget to enforce" and turned
OFF the cap, enabling unbounded subagent burn.

This module provides the canonical entry point:

    :func:`enforce_budget_on_zero_cost_with_work_events`

which the orchestrator MUST call instead of silently skipping budget
enforcement when reported cost is zero.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash → cost=0.0 (free retry).
* cost > 0 → normal case → returned as-is.

Threshold
---------
Default: 100 work events (env BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD,
clamped to [1, 10000]).

Relationship to cost_telemetry_guard
--------------------------------------
:mod:`bob3.orchestrator.cost_telemetry_guard` already contains
``is_cost_telemetry_lost``, ``apply_pessimistic_cost``, and
``emit_cost_telemetry_lost_event``.  This module delegates to those
primitives and exposes the unified function under the name the ACs require:
``enforce_budget_on_zero_cost_with_work_events``.
"""

from __future__ import annotations

from bob3.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult as _EnforceBudgetResult,
    enforce_budget_on_zero_cost as _enforce_budget_on_zero_cost,
    is_cost_telemetry_lost as _is_cost_telemetry_lost,
    apply_pessimistic_cost as _apply_pessimistic_cost,
)


class EnforceBudgetWithWorkEventsResult:
    """Result returned by :func:`enforce_budget_on_zero_cost_with_work_events`.

    Attributes
    ----------
    cost_to_charge:
        The cost to record and charge against the budget. Equals
        ``per_feature_ceiling`` when ``telemetry_lost`` is True;
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
            f"EnforceBudgetWithWorkEventsResult("
            f"cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def validate_cost_nonzero(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> EnforceBudgetWithWorkEventsResult:
    """Validate that reported cost is not treated as zero when telemetry may be lost.

    When ``reported_cost`` is zero (or None/negative) AND ``work_events``
    exceeds the telemetry-loss threshold, the cost is classified as
    UNKNOWN-but-nonzero and ``per_feature_ceiling`` is charged instead.

    This enforces the invariant: zero-reported-cost MUST NOT disable budget
    enforcement when substantial work was observed.

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied as a pessimistic charge when
        telemetry is lost.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    EnforceBudgetWithWorkEventsResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.
    """
    inner: _EnforceBudgetResult = _enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
    return EnforceBudgetWithWorkEventsResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )


def enforce_cost_with_work_events(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> EnforceBudgetWithWorkEventsResult:
    """Canonical AC-required entry point: zero-cost MUST NOT disable budget enforcement.

    Alias for :func:`enforce_budget_on_zero_cost_with_work_events`.
    Parameters and return value are identical.
    """
    return enforce_budget_on_zero_cost_with_work_events(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def apply_ceiling_on_telemetry_loss(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
) -> float:
    """Apply the per-feature ceiling cost when stream-json telemetry is lost.

    Returns ``per_feature_ceiling`` when cost telemetry is detected as lost
    (cost==0 AND work_events > threshold). Returns the reported cost unchanged
    for all other cases (positive cost or genuine spawn-crash with zero work).

    This function is the direct cost-application primitive; callers that need
    structured event logging should use :func:`validate_cost_nonzero` or
    :func:`enforce_budget_on_zero_cost_with_work_events` instead.

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling to apply when telemetry is lost.

    Returns
    -------
    float
        The cost to charge: ``per_feature_ceiling`` when telemetry is lost,
        or the reported cost (possibly 0.0 for genuine free-retry) otherwise.
    """
    is_lost = _is_cost_telemetry_lost(
        reported_cost=reported_cost,
        work_events=work_events,
    )
    return _apply_pessimistic_cost(
        reported_cost=reported_cost,
        is_lost=is_lost,
        per_feature_ceiling=per_feature_ceiling,
    )


def enforce_budget_on_zero_cost_with_work_events(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> EnforceBudgetWithWorkEventsResult:
    """Detect stream-json telemetry loss and enforce the budget ceiling.

    This function MUST be called whenever the orchestrator observes
    reported_cost==0 after a sub-agent run. It enforces the design
    invariant that zero-cost NEVER disables budget enforcement when
    substantial work was done.

    Parameters
    ----------
    reported_cost:
        The raw cost from the SDK (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling, applied as a pessimistic charge
        when telemetry is lost (env BOB3_PER_FEATURE_COST_CEILING).
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    EnforceBudgetWithWorkEventsResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling.
    - cost==0 AND work_events == 0 → genuine spawn crash → cost=0.0 (free retry).
    - cost > 0 → normal → returned as-is.
    """
    inner: _EnforceBudgetResult = _enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
    return EnforceBudgetWithWorkEventsResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )
