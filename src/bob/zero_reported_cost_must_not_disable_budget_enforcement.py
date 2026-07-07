"""da0085c2: zero-reported-cost MUST NOT disable budget enforcement.

When the stream-json parser loses cost-delta events during a mid-work crash
or parser regression, the reported cost arrives as zero even though the
sub-agent consumed real resources. The unsafe path interprets cost==0 as
"no budget to enforce" and disables the cap entirely — enabling runaway
subagent burn precisely under the crash conditions where enforcement is
most needed.

This module exposes a single canonical entry point:

    :func:`zero_reported_cost_must_not_disable_budget_enforcement`

which the orchestrator MUST call instead of treating cost==0 as a
signal to disable enforcement.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge per-feature ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash → cost=0.0 (free retry, F-R7-478).
* cost > 0 → normal case → returned as-is.

Threshold
---------
Default: 100 work events (env ``BOB_COST_TELEMETRY_LOST_WORK_THRESHOLD``,
clamped to [1, 10000]).
"""

from __future__ import annotations

from bob.orchestrator.cost_telemetry_guard import (
    EnforceBudgetResult,
    enforce_budget_on_zero_cost,
)

__all__ = [
    "zero_reported_cost_must_not_disable_budget_enforcement",
    "apply_cost_telemetry_lost_ceiling",
    "ZeroCostEnforcementResult",
]


class ZeroCostEnforcementResult:
    """Result returned by :func:`zero_reported_cost_must_not_disable_budget_enforcement`.

    Attributes
    ----------
    cost_to_charge:
        The cost to record against the budget. Equals ``per_feature_ceiling``
        when ``telemetry_lost`` is True; equals the SDK-reported cost otherwise
        (possibly 0.0 for a genuine free-retry spawn crash).
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
            f"ZeroCostEnforcementResult("
            f"cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def zero_reported_cost_must_not_disable_budget_enforcement(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> ZeroCostEnforcementResult:
    """Enforce budget when zero reported cost may indicate stream-json telemetry loss.

    Implements the fix for the observed incident: feature 9b2e1060 crashed with
    work_events=176217 and reported_cost=0, causing the orchestrator to log
    "Cost is zero — budget enforcement disabled" and skip enforcement entirely.
    A zero cost combined with high work_events is a telemetry parse failure,
    not a free run. This function MUST be called to prevent that failure mode.

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
    ZeroCostEnforcementResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN log.
    - cost==0 AND work_events == 0 → genuine spawn crash → cost=0.0 (free retry).
    - cost > 0 → normal → returned as-is.
    """
    inner: EnforceBudgetResult = enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
    return ZeroCostEnforcementResult(
        cost_to_charge=inner.cost_to_charge,
        telemetry_lost=inner.telemetry_lost,
    )


def apply_cost_telemetry_lost_ceiling(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> ZeroCostEnforcementResult:
    """Apply the per-feature ceiling when zero cost signals stream-json telemetry loss.

    AC-mandated entry point. This is the strict variant of
    :func:`zero_reported_cost_must_not_disable_budget_enforcement`: it validates
    that ``per_feature_ceiling`` is a usable positive charge BEFORE deciding
    anything, so a caller cannot silently pass an invalid ceiling that would
    later collapse budget enforcement back to a no-op.

    The orchestrator MUST call this instead of interpreting ``cost == 0`` as
    "no budget to enforce". When cost is zero AND ``work_events`` exceed the
    threshold, the cost is treated as UNKNOWN-but-nonzero and the ceiling is
    charged as if the sub-agent had consumed the full ceiling for that attempt.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling. Must be positive (> 0); raises ValueError
        otherwise — budget enforcement cannot operate without a positive ceiling.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    ZeroCostEnforcementResult
        ``.cost_to_charge`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0.
    """
    if not isinstance(per_feature_ceiling, (int, float)) or per_feature_ceiling <= 0:
        raise ValueError(
            f"apply_cost_telemetry_lost_ceiling: per_feature_ceiling must be a "
            f"positive number, got {per_feature_ceiling!r}. Budget enforcement "
            f"requires a positive ceiling — a zero or negative ceiling would "
            f"re-enable the runaway-burn failure mode this guard prevents."
        )
    return zero_reported_cost_must_not_disable_budget_enforcement(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
