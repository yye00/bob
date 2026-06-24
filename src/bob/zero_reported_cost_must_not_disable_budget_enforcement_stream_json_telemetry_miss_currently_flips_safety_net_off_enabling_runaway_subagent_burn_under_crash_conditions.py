"""0fb1a803: zero-reported-cost MUST NOT disable budget enforcement.

When the stream-json parser loses cost-delta events (e.g. due to a
mid-work crash or parser regression), reported cost arrives as zero even
though the sub-agent consumed real resources. The previous enforcement path
interpreted cost==0 as "no budget to enforce" and disabled the cap entirely
— the opposite of the safe behavior.

This module exposes a single canonical entry point whose name matches the
feature AC exactly, delegating to the primitives in
:mod:`bob.orchestrator.cost_telemetry_guard`.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge per-feature ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash (free retry via F-R7-478).
* cost > 0 → normal case → returned as-is.

Threshold
---------
Default: 100 work events (env ``BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD``,
clamped to [1, 10000]).
"""

from __future__ import annotations

from bob.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult as _EnforceBudgetResult,
    enforce_budget_on_zero_cost as _enforce_budget_on_zero_cost,
)


class ZeroReportedCostEnforcementResult:
    """Result returned by the zero-cost budget enforcement function.

    Attributes
    ----------
    cost_to_charge:
        The cost to record against the budget. Equals ``per_feature_ceiling``
        when ``telemetry_lost`` is True; equals the SDK-reported cost otherwise
        (possibly 0.0 for a genuine free-retry spawn crash).
    telemetry_lost:
        True when cost==0 AND work_events > threshold (stream-json miss
        requiring pessimistic charge).
    """

    __slots__ = ("cost_to_charge", "telemetry_lost")

    def __init__(self, cost_to_charge: float, telemetry_lost: bool) -> None:
        self.cost_to_charge = float(cost_to_charge)
        self.telemetry_lost = bool(telemetry_lost)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ZeroReportedCostEnforcementResult("
            f"cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def zero_reported_cost_must_not_disable_budget_enforcement_stream_json_telemetry_miss_currently_flips_safety_net_off_enabling_runaway_subagent_burn_under_crash_conditions(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> ZeroReportedCostEnforcementResult:
    """Enforce budget when zero reported cost may indicate stream-json telemetry loss.

    Implements the fix for the observed incident where feature 9b2e1060
    crashed with work_events=176217 and cost=0, causing the orchestrator to
    disable budget enforcement. A zero cost combined with high work_events is
    a telemetry parse failure, not a free run.

    This function MUST be called whenever the orchestrator observes
    reported_cost==0 after a sub-agent run. It ensures zero-cost NEVER
    disables budget enforcement when substantial work was done.

    Parameters
    ----------
    reported_cost:
        The raw cost from the SDK (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling, applied pessimistically when telemetry
        is lost (env ``BOB_PER_FEATURE_COST_CEILING``).
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    ZeroReportedCostEnforcementResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN event.
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
    return ZeroReportedCostEnforcementResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )
