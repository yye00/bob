"""dd04e2b3: Zero-reported-cost MUST NOT disable budget enforcement.

When a sub-agent crashes with stream-json parser failure, the reported cost
arrives as zero even though the agent consumed real resources (observable via
work_events). The unsafe path would interpret cost==0 as "no budget to enforce"
and disable the cap — enabling unbounded subagent burn under crash conditions.

This module provides the canonical validation entry point:

    :func:`validate_cost_and_work_events`

which the orchestrator MUST call to determine whether reported telemetry is
trustworthy or indicates a stream-json parser miss.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge per-feature ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash → cost=0.0 (F-R7-478 free retry).
* cost > 0 → normal case → returned as-is.

A ``cost_telemetry_lost`` structured WARN event is emitted whenever the
pessimistic ceiling is applied, containing (feature_id, work_events, exit_code,
attempt) for operator triage.

Threshold
---------
Default: 100 work events (env ``BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD``,
clamped to [1, 10000]).
"""

from __future__ import annotations

import logging

from bob.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult,
    enforce_budget_on_zero_cost,
    is_cost_telemetry_lost,
)

__all__ = [
    "validate_cost_and_work_events",
    "CostTelemetryValidationResult",
]

logger = logging.getLogger(__name__)


class CostTelemetryValidationResult:
    """Result returned by :func:`validate_cost_and_work_events`.

    Attributes
    ----------
    cost_to_charge:
        The cost to record against the budget. Equals ``per_feature_ceiling``
        when ``telemetry_lost`` is True (pessimistic enforcement applied);
        equals the SDK-reported cost otherwise (possibly 0.0 for a genuine
        free-retry spawn crash where no budget was consumed).
    telemetry_lost:
        True when cost==0 AND work_events > threshold — stream-json parser
        dropped cost-delta events during the crash. Budget enforcement is
        applied via the per-feature ceiling in this case.
    """

    __slots__ = ("cost_to_charge", "telemetry_lost")

    def __init__(self, cost_to_charge: float, telemetry_lost: bool) -> None:
        self.cost_to_charge = float(cost_to_charge)
        self.telemetry_lost = bool(telemetry_lost)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CostTelemetryValidationResult("
            f"cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def validate_cost_and_work_events(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostTelemetryValidationResult:
    """Validate reported cost against work events to prevent enforcement bypass.

    Implements the fix for the observed incident: feature 9b2e1060 crashed with
    work_events=176217 and reported_cost=0, causing the orchestrator to log
    "Cost is zero — budget enforcement disabled for this feature" and skip
    enforcement entirely. A zero cost combined with high work_events is a
    stream-json telemetry parse failure, not a free run.

    This function MUST be called whenever budget enforcement is being evaluated.
    It prevents the failure mode where cost==0 is incorrectly treated as
    "no budget to enforce" — specifically under the crash conditions where
    enforcement is most needed.

    Parameters
    ----------
    reported_cost:
        The raw cost from the SDK (total_cost_usd). None is coerced to 0.0.
        Negative values are also treated as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl. Used to
        distinguish genuine spawn-crash (work_events==0) from telemetry-loss
        crash (work_events > threshold).
    per_feature_ceiling:
        Per-feature max-cost ceiling applied pessimistically when telemetry
        is lost. Source: env ``BOB_PER_FEATURE_COST_CEILING``.
    feature_id:
        Feature UUID for structured logging of the ``cost_telemetry_lost`` event.
    exit_code:
        Sub-agent exit code (None if unknown). Included in the structured log.
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    CostTelemetryValidationResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0. Budget enforcement cannot operate
        without a positive ceiling.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN log, charge refinement attempt.
    - cost==0 AND work_events == 0 → genuine spawn crash → cost=0.0 (free retry
      via F-R7-478; budget enforcement remains active — no charge means no
      progress toward ceiling, which is correct).
    - cost > 0 → normal → returned as-is.
    - MUST NOT disable enforcement on zero-cost; always returns a result with
      enforcement applied when work was observed.
    """
    if per_feature_ceiling <= 0:
        raise ValueError(
            f"validate_cost_and_work_events: per_feature_ceiling must be positive, "
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
    return CostTelemetryValidationResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )
