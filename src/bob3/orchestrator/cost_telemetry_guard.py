"""fbe6b19b: Zero-cost telemetry loss guard for budget enforcement.

When a sub-agent crashes, the stream-json parser may fail to deliver
cost-delta events, causing reported_cost==0 even though the agent did
substantial work (observable via work_events from progress.jsonl).

The existing code at that point logged a warning and disabled budget
enforcement entirely — the opposite of the safe behavior. This module
provides four functions that the run_loop budget-enforcement path
calls instead:

1. :func:`is_cost_telemetry_lost` — detects the ambiguous case.
2. :func:`apply_pessimistic_cost` — returns the per-feature ceiling
   as a conservative charge when telemetry is lost.
3. :func:`emit_cost_telemetry_lost_event` — writes a structured WARN
   log so operators can grep for the event.
4. :func:`enforce_budget_on_zero_cost` — unified entry point that
   combines detection, application, and event emission.

Design invariant
----------------
Pure zero-work zero-cost (work_events==0) is NOT telemetry loss — it
is a genuine spawn-time crash with no work done. That case continues
to flow through the F-R7-478 free-retry path unaffected.

Only when cost==0 AND work_events > threshold do we classify the
zero-cost as "telemetry lost" and apply the pessimistic ceiling.

Threshold
---------
Default: 100 work events (env BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD,
clamped to [1, 10000]).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_WORK_THRESHOLD = 100
_MIN_THRESHOLD = 1
_MAX_THRESHOLD = 10000


def _read_threshold() -> int:
    """Read BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD, clamped to [1, 10000]."""
    raw = os.environ.get("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "")
    if raw:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_WORK_THRESHOLD
        return max(_MIN_THRESHOLD, min(_MAX_THRESHOLD, value))
    return _DEFAULT_WORK_THRESHOLD


def is_cost_telemetry_lost(
    reported_cost: float | None,
    work_events: int,
) -> bool:
    """Return True when cost==0 AND work_events > threshold (telemetry miss).

    Parameters
    ----------
    reported_cost:
        The raw cost value from the SDK (total_cost_usd). None is
        coerced to 0.0. Negative values are also treated as 0.0.
    work_events:
        Count of substantive progress events in progress.jsonl.
        Provided by the crash_classifier / caller from on-disk evidence.

    Returns
    -------
    bool
        True  — cost is zero AND work_events > threshold: telemetry loss.
        False — cost > 0 (telemetry was delivered), OR work_events == 0
                (genuine spawn crash with no work, not telemetry loss).
    """
    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0
    if cost > 0.0:
        return False
    threshold = _read_threshold()
    return work_events > threshold


def apply_pessimistic_cost(
    reported_cost: float | None,
    is_lost: bool,
    per_feature_ceiling: float,
) -> float:
    """Return the cost to charge given the telemetry-loss verdict.

    Parameters
    ----------
    reported_cost:
        The SDK-reported cost. Used only when ``is_lost`` is False.
    is_lost:
        Result of :func:`is_cost_telemetry_lost`.
    per_feature_ceiling:
        The per-feature max-cost ceiling configured for this run.
        Applied when ``is_lost`` is True.

    Returns
    -------
    float
        If ``is_lost``: ``per_feature_ceiling`` (pessimistic safe charge).
        Otherwise: ``reported_cost`` (exact SDK value, possibly 0.0 for
        genuine spawn crashes that belong to the free-retry path).
    """
    if is_lost:
        return float(per_feature_ceiling)
    cost = float(reported_cost) if reported_cost is not None else 0.0
    return max(0.0, cost)


def emit_cost_telemetry_lost_event(
    feature_id: str,
    work_events: int,
    exit_code: int | None,
    attempt_number: int,
    applied_pessimistic_cost: float,
) -> None:
    """Emit a structured WARN log for the cost_telemetry_lost event.

    Parameters
    ----------
    feature_id:
        Feature that triggered the detection.
    work_events:
        Count of work events observed in progress.jsonl.
    exit_code:
        The sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).
    applied_pessimistic_cost:
        The ceiling cost that was charged in place of the missing telemetry.
    """
    logger.warning(
        "cost_telemetry_lost: feature_id=%s work_events=%d exit_code=%s "
        "attempt=%d applied_pessimistic_cost=%.4f — "
        "reported cost was 0 but work_events > threshold; "
        "applying per-feature ceiling to preserve budget enforcement.",
        feature_id,
        work_events,
        exit_code,
        attempt_number,
        applied_pessimistic_cost,
    )


class EnforceBudgetResult:
    """Result returned by :func:`enforce_budget_on_zero_cost`.

    Attributes
    ----------
    cost_to_charge:
        The cost that should be recorded and charged against the budget.
        If ``telemetry_lost`` is True, this equals ``per_feature_ceiling``.
        Otherwise, it equals the SDK-reported cost (possibly 0.0 for a
        genuine free-retry spawn crash).
    telemetry_lost:
        True when cost==0 AND work_events > threshold (stream-json miss
        requiring pessimistic charge). False for normal or free-retry cases.
    """

    __slots__ = ("cost_to_charge", "telemetry_lost")

    def __init__(self, cost_to_charge: float, telemetry_lost: bool) -> None:
        self.cost_to_charge = cost_to_charge
        self.telemetry_lost = telemetry_lost

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"EnforceBudgetResult(cost_to_charge={self.cost_to_charge!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def enforce_budget_on_zero_cost(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> EnforceBudgetResult:
    """Unified entry point: detect telemetry loss, apply pessimistic cost, emit event.

    This function MUST be called whenever the orchestrator sees reported_cost==0
    after a sub-agent run. It enforces the design invariant that zero-cost NEVER
    disables budget enforcement when substantial work was done.

    Behavior
    --------
    - If ``reported_cost == 0`` AND ``work_events > threshold``:
        telemetry is considered lost. The per-feature ceiling is charged
        and a structured ``cost_telemetry_lost`` WARN event is emitted.
    - If ``reported_cost == 0`` AND ``work_events == 0``:
        genuine spawn-time crash; cost returned as 0.0 so the F-R7-478
        free-retry path fires (budget enforcement remains active — no
        charge means no progress toward the ceiling, which is correct).
    - If ``reported_cost > 0``:
        normal case; reported cost is returned unmodified.

    Parameters
    ----------
    reported_cost:
        The raw cost value from the SDK (total_cost_usd). None coerced to 0.0.
    work_events:
        Count of substantive progress events in progress.jsonl.
    per_feature_ceiling:
        The per-feature max-cost ceiling (e.g. from BOB3_PER_FEATURE_COST_CEILING).
    feature_id:
        Feature ID for structured log output.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).

    Returns
    -------
    EnforceBudgetResult
        ``.cost_to_charge`` is the amount to record; ``.telemetry_lost``
        indicates whether the pessimistic ceiling was applied.
    """
    is_lost = is_cost_telemetry_lost(reported_cost=reported_cost, work_events=work_events)
    cost_to_charge = apply_pessimistic_cost(
        reported_cost=reported_cost,
        is_lost=is_lost,
        per_feature_ceiling=per_feature_ceiling,
    )
    if is_lost:
        emit_cost_telemetry_lost_event(
            feature_id=feature_id,
            work_events=work_events,
            exit_code=exit_code,
            attempt_number=attempt_number,
            applied_pessimistic_cost=cost_to_charge,
        )
    return EnforceBudgetResult(cost_to_charge=cost_to_charge, telemetry_lost=is_lost)


def enforce_budget_with_cost_telemetry_fallback(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> EnforceBudgetResult:
    """Budget enforcement with automatic telemetry-loss fallback.

    Alias for :func:`enforce_budget_on_zero_cost` that satisfies the AC
    requiring the name ``enforce_budget_with_cost_telemetry_fallback`` in
    ``bob3.orchestrator``.

    When reported cost is zero AND work_events exceed the threshold, this
    function treats the zero as a telemetry miss (not a free run) and applies
    the per-feature ceiling as a pessimistic charge. This ensures budget
    enforcement is NEVER disabled by a stream-json parser regression.

    Parameters
    ----------
    reported_cost:
        The raw cost value from the SDK. None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied when telemetry is lost.
    feature_id:
        Feature ID for structured log output.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).

    Returns
    -------
    EnforceBudgetResult
        ``.cost_to_charge`` is the amount to record; ``.telemetry_lost``
        indicates whether the pessimistic ceiling was applied.
    """
    return enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def enforce_budget_with_telemetry_loss(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> EnforceBudgetResult:
    """Budget enforcement that treats zero-cost + high work_events as telemetry loss.

    Satisfies AC: Function defined: bob3.orchestrator.enforce_budget_with_telemetry_loss

    When reported cost is zero AND work_events exceed the threshold, this
    function treats the zero as a telemetry miss (not a free run) and applies
    the per-feature ceiling as a pessimistic charge. This ensures budget
    enforcement is NEVER disabled by a stream-json parser regression.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit cost_telemetry_lost WARN event.
    - cost==0 AND work_events == 0 → genuine spawn crash → charge 0.0
      (F-R7-478 free-retry path; budget enforcement remains active).
    - cost > 0 → normal → returned as-is.

    Parameters
    ----------
    reported_cost:
        The raw cost value from the SDK. None coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied when telemetry is lost.
    feature_id:
        Feature ID for structured log output.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).

    Returns
    -------
    EnforceBudgetResult
        ``.cost_to_charge`` is the amount to record; ``.telemetry_lost``
        indicates whether the pessimistic ceiling was applied.
    """
    return enforce_budget_on_zero_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
