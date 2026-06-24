"""b621f23b: Zero-reported-cost MUST NOT disable budget enforcement.

When a sub-agent crashes, the stream-json parser may fail to deliver cost-delta
events, leaving reported_cost==0.  The original code interpreted this as "no
budget to enforce" and disabled the cap entirely — the opposite of safe behaviour.

This module provides:

    :func:`validate_reported_cost` — unified entry point for the orchestrator.
        Detects telemetry loss (cost==0 AND work_events > threshold) and returns
        the effective cost to charge together with a telemetry_lost flag.

    :func:`log_cost_telemetry_lost` — emits a structured WARN log event with all
        relevant fields so operators can grep for ``cost_telemetry_lost``.

Design invariant
----------------
* cost==0 AND work_events > threshold → telemetry lost → charge per-feature ceiling.
* cost==0 AND work_events == 0 → genuine spawn-crash → cost=0.0 (F-R7-478 free retry).
* cost > 0 → normal case → returned as-is.

Threshold
---------
Default: 100 work events (env ``BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD``,
clamped to [1, 10000]).

Integration
-----------
This module delegates detection and application to the lower-level primitives
in :mod:`bob3.orchestrator.cost_telemetry_guard`.  The orchestrator's
``__init__.py`` must expose ``validate_reported_cost`` and
``log_cost_telemetry_lost`` to satisfy the integration AC.
"""

from __future__ import annotations

import logging

from bob3.orchestrator.cost_telemetry_guard import (
    is_cost_telemetry_lost,
    apply_pessimistic_cost,
    emit_cost_telemetry_lost_event,
)

__all__ = [
    "validate_reported_cost",
    "log_cost_telemetry_lost",
    "CostValidationResult",
    "validate_cost_and_events",
    "validate_cost_and_work_events",
    "should_treat_cost_as_unknown",
    "should_apply_max_cost_ceiling",
    "enforce_zero_cost_policy",
    "enforce_zero_cost_protection",
    "should_enforce_budget",
]

logger = logging.getLogger(__name__)


class CostValidationResult:
    """Result of :func:`validate_reported_cost`.

    Attributes
    ----------
    effective_cost:
        The cost to record and charge against the budget.
        Equals ``per_feature_ceiling`` when ``telemetry_lost`` is True;
        equals the SDK-reported cost otherwise (possibly 0.0 for a
        genuine free-retry spawn crash).
    telemetry_lost:
        True when cost==0 AND work_events > threshold (stream-json miss
        requiring pessimistic charge). False for normal or free-retry cases.
    """

    __slots__ = ("effective_cost", "telemetry_lost")

    def __init__(self, effective_cost: float, telemetry_lost: bool) -> None:
        self.effective_cost = float(effective_cost)
        self.telemetry_lost = bool(telemetry_lost)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CostValidationResult("
            f"effective_cost={self.effective_cost!r}, "
            f"telemetry_lost={self.telemetry_lost!r})"
        )


def log_cost_telemetry_lost(
    feature_id: str,
    work_events: int,
    exit_code: int | None,
    attempt_number: int,
    applied_pessimistic_cost: float,
) -> None:
    """Emit a structured WARN log for the cost_telemetry_lost event.

    Operators and incident-response tooling can grep for the literal string
    ``cost_telemetry_lost`` to locate these events.

    Parameters
    ----------
    feature_id:
        Feature UUID that triggered the detection.
    work_events:
        Count of work events observed in progress.jsonl.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based).
    applied_pessimistic_cost:
        The ceiling cost charged in place of the missing telemetry.
    """
    emit_cost_telemetry_lost_event(
        feature_id=feature_id,
        work_events=work_events,
        exit_code=exit_code,
        attempt_number=attempt_number,
        applied_pessimistic_cost=applied_pessimistic_cost,
    )
    logger.warning(
        "cost_telemetry_lost: feature_id=%s work_events=%d exit_code=%s "
        "attempt=%d applied_pessimistic_cost=%.4f",
        feature_id,
        work_events,
        exit_code,
        attempt_number,
        applied_pessimistic_cost,
    )


def validate_reported_cost(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostValidationResult:
    """Validate reported cost and enforce budget when telemetry may be lost.

    This is the single entry-point the orchestrator MUST call instead of
    treating cost==0 as "no budget to enforce."

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None is coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied as a pessimistic charge when
        telemetry is lost (env ``BOB3_PER_FEATURE_COST_CEILING``).
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    CostValidationResult
        ``.effective_cost`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN log.
    - cost==0 AND work_events == 0 → genuine spawn crash → effective_cost=0.0
      (F-R7-478 free-retry path fires; budget enforcement remains active).
    - cost > 0 → normal → returned as-is.
    """
    is_lost = is_cost_telemetry_lost(
        reported_cost=reported_cost,
        work_events=work_events,
    )
    effective_cost = apply_pessimistic_cost(
        reported_cost=reported_cost,
        is_lost=is_lost,
        per_feature_ceiling=per_feature_ceiling,
    )
    if is_lost:
        log_cost_telemetry_lost(
            feature_id=feature_id,
            work_events=work_events,
            exit_code=exit_code,
            attempt_number=attempt_number,
            applied_pessimistic_cost=effective_cost,
        )
    return CostValidationResult(
        effective_cost=effective_cost,
        telemetry_lost=is_lost,
    )


def should_treat_cost_as_unknown(
    reported_cost: float | None,
    work_events: int,
) -> bool:
    """Return True when cost telemetry is ambiguous and must be treated as unknown.

    The cost is considered unknown (not zero) when reported_cost is zero (or
    None/negative) AND work_events exceeds the telemetry-loss threshold.  This
    is the signal that the stream-json parser dropped cost-delta events during a
    crash, leaving a misleading zero rather than a true free run.

    Wraps :func:`bob3.orchestrator.cost_telemetry_guard.is_cost_telemetry_lost`
    and exists as the named AC predicate so callers have a single, clearly-named
    entry point.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.

    Returns
    -------
    bool
        True  — treat cost as UNKNOWN-but-nonzero (apply pessimistic ceiling).
        False — cost is either positive (normal) or work_events == 0 (free retry).
    """
    return is_cost_telemetry_lost(
        reported_cost=reported_cost,
        work_events=work_events,
    )


def validate_cost_and_events(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostValidationResult:
    """Validate cost + work_events, enforcing budget when telemetry may be lost.

    Named AC entry point combining detection (:func:`should_treat_cost_as_unknown`)
    with pessimistic cost application and structured event logging.  This is the
    function the orchestrator MUST call instead of treating cost==0 as "no budget
    to enforce."

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are coerced to 0.0.
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
    CostValidationResult
        ``.effective_cost`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN log.
    - cost==0 AND work_events == 0 → genuine spawn crash → effective_cost=0.0
      (F-R7-478 free-retry path; budget enforcement remains active).
    - cost > 0 → normal → returned as-is.
    """
    return validate_reported_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def enforce_zero_cost_policy(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostValidationResult:
    """Enforce the zero-cost policy: zero-reported-cost MUST NOT disable budget enforcement.

    Named AC entry point. When reported_cost is zero (or None/negative) AND
    work_events exceed the threshold, the cost is treated as UNKNOWN-but-nonzero
    and the per-feature ceiling is applied as a pessimistic charge. This ensures
    that a stream-json parser regression or crash-induced telemetry loss NEVER
    converts the budget guard into a no-op.

    Raises ValueError for invalid per_feature_ceiling (negative or zero).

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling. Must be positive (> 0); raises ValueError
        otherwise so callers cannot silently pass an invalid ceiling.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    CostValidationResult
        ``.effective_cost`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0 (invalid ceiling — budget enforcement
        cannot operate without a positive ceiling).

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling.
    - cost==0 AND work_events == 0 → genuine spawn crash → effective_cost=0.0.
    - cost > 0 → normal → returned as-is.
    """
    if per_feature_ceiling <= 0:
        raise ValueError(
            f"enforce_zero_cost_policy: per_feature_ceiling must be positive, "
            f"got {per_feature_ceiling!r}. Budget enforcement requires a positive ceiling."
        )
    return validate_reported_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def should_enforce_budget(
    reported_cost: float | None,
    work_events: int,
) -> bool:
    """Return True when budget enforcement MUST proceed, regardless of reported cost.

    This is the named AC predicate for the core invariant:
    zero-reported-cost MUST NOT disable budget enforcement.

    Budget enforcement is ALWAYS required (returns True) except for the single
    case of a genuine spawn-crash with zero work (work_events == 0 AND
    cost == 0), which is the F-R7-478 free-retry path where no budget was
    consumed.

    When reported_cost is zero (or None/negative) AND work_events exceed the
    telemetry-loss threshold, the cost is ambiguous (stream-json parser may
    have dropped cost-delta events during a crash). In this case enforcement
    is still required — the caller should apply the pessimistic ceiling via
    :func:`validate_reported_cost` or :func:`enforce_zero_cost_policy`.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are treated as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.

    Returns
    -------
    bool
        True  — budget enforcement MUST proceed (covers: cost > 0, and
                cost == 0 with work_events > 0 i.e. work was observed).
        False — ONLY for genuine spawn-crash free-retry: cost == 0 AND
                work_events == 0 (no work was done, no budget consumed).
    """
    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0

    if cost > 0.0:
        return True

    # cost == 0: enforce if any work was observed (telemetry loss) or if telemetry guard detects it
    return work_events > 0 or is_cost_telemetry_lost(reported_cost=reported_cost, work_events=work_events)


def validate_cost_and_work_events(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostValidationResult:
    """Named AC entry point: validate cost + work_events, enforcing budget when telemetry may be lost.

    This is the function the orchestrator MUST call instead of treating cost==0 as
    "no budget to enforce." Named to match the AC predicate
    ``bob3.cost_enforcement.validate_cost_and_work_events``.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling applied as a pessimistic charge when
        telemetry is lost. Must be positive; raises ValueError otherwise.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    CostValidationResult
        ``.effective_cost`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling,
      emit ``cost_telemetry_lost`` WARN log.
    - cost==0 AND work_events == 0 → genuine spawn crash → effective_cost=0.0
      (F-R7-478 free-retry path; budget enforcement remains active).
    - cost > 0 → normal → returned as-is.
    """
    if per_feature_ceiling <= 0:
        raise ValueError(
            f"validate_cost_and_work_events: per_feature_ceiling must be positive, "
            f"got {per_feature_ceiling!r}. Budget enforcement requires a positive ceiling."
        )
    return validate_reported_cost(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )


def should_apply_max_cost_ceiling(
    reported_cost: float | None,
    work_events: int,
) -> bool:
    """Named AC predicate: return True when the per-feature max-cost ceiling MUST be applied.

    The ceiling is applied when reported cost is zero (or None/negative) AND
    work_events exceed the telemetry-loss threshold — the signal that the stream-json
    parser dropped cost-delta events during a crash, leaving a misleading zero rather
    than a true free run. In this case the orchestrator MUST apply the pessimistic
    ceiling rather than treating cost==0 as "no budget to enforce."

    Named to match the AC predicate ``bob3.cost_enforcement.should_apply_max_cost_ceiling``.
    Wraps :func:`bob3.orchestrator.cost_telemetry_guard.is_cost_telemetry_lost`.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.

    Returns
    -------
    bool
        True  — apply the per-feature max-cost ceiling (telemetry loss detected).
        False — ceiling not needed (cost > 0, or work_events == 0 free-retry).
    """
    return is_cost_telemetry_lost(
        reported_cost=reported_cost,
        work_events=work_events,
    )


def enforce_zero_cost_protection(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> CostValidationResult:
    """Enforce budget protection when reported cost is zero — the AC-named entry point.

    Zero-reported-cost MUST NOT disable budget enforcement. When a sub-agent crashes,
    the stream-json parser may fail to deliver cost-delta events, leaving reported_cost==0.
    This function ensures that such telemetry loss is detected and the per-feature
    ceiling is applied pessimistically, preventing unbounded subagent burn.

    This is the canonical AC function (``bob3.cost_enforcement.enforce_zero_cost_protection``).
    It delegates to :func:`enforce_zero_cost_policy` which raises ``ValueError`` on
    an invalid (non-positive) ceiling.

    Parameters
    ----------
    reported_cost:
        Raw SDK cost (total_cost_usd). None and negative values are coerced to 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.
    per_feature_ceiling:
        Per-feature max-cost ceiling. Must be positive (> 0); raises ValueError otherwise.
    feature_id:
        Feature UUID for structured logging.
    exit_code:
        Sub-agent exit code (None if unknown).
    attempt_number:
        Current refinement attempt number (1-based), for structured logging.

    Returns
    -------
    CostValidationResult
        ``.effective_cost`` — amount to record against the budget.
        ``.telemetry_lost`` — True when the pessimistic ceiling was applied.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0.

    Behavior
    --------
    - cost==0 AND work_events > threshold → telemetry lost → charge ceiling.
    - cost==0 AND work_events == 0 → genuine spawn crash → effective_cost=0.0.
    - cost > 0 → normal → returned as-is.
    """
    return enforce_zero_cost_policy(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
