"""354499d7: Zero-reported-cost MUST NOT disable budget enforcement.

When a sub-agent crashes mid-work, the stream-json parser may fail to deliver
cost-delta events, leaving reported_cost==0.  The old code interpreted this as
"no budget to enforce" and disabled the cap entirely.  This module provides
``enforce_cost_ceiling`` as the canonical entry point that the orchestrator MUST
call instead of treating zero cost as a free pass.

Design
------
- cost==0 AND work_events > threshold → telemetry lost → charge per-feature ceiling.
- cost==0 AND work_events == 0 → genuine spawn-crash → effective_cost=0.0 (free retry).
- cost > 0 → normal → returned as-is.

Threshold
---------
Default: 100 work events (env ``BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD``,
clamped to [1, 10000]).
"""

from __future__ import annotations

import logging
import os
from typing import NamedTuple

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 100
_MIN_THRESHOLD = 1
_MAX_THRESHOLD = 10000


class TelemetryLossResult(NamedTuple):
    """Result of :func:`detect_cost_telemetry_loss`."""
    telemetry_lost: bool
    effective_cost: float


def _read_threshold() -> int:
    raw = os.environ.get("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "")
    if raw:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_THRESHOLD
        return max(_MIN_THRESHOLD, min(_MAX_THRESHOLD, value))
    return _DEFAULT_THRESHOLD


def enforce_cost_ceiling(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> float:
    """Enforce budget ceiling, returning effective cost that must be charged.

    When reported_cost is zero AND work_events exceed the telemetry-loss
    threshold, the cost is UNKNOWN-but-nonzero.  The per-feature ceiling is
    applied as a pessimistic charge and a structured ``cost_telemetry_lost``
    WARN event is emitted.

    This is the canonical integration entry point the orchestrator's run_loop
    MUST call.  It MUST NOT return 0.0 in the telemetry-loss case, which is
    what the old "disable enforcement on zero" bug did.

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None coerced to 0.0.
        Negative values treated as 0.0.
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
    float
        Effective cost to charge against the budget:
        - ``per_feature_ceiling`` when telemetry is lost (cost==0 and
          work_events > threshold).
        - 0.0 when it is a genuine free-retry spawn crash (cost==0 and
          work_events == 0).
        - The raw reported_cost otherwise.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0 (budget enforcement requires a
        positive ceiling to operate correctly).
    """
    if per_feature_ceiling <= 0:
        raise ValueError(
            f"enforce_cost_ceiling: per_feature_ceiling must be positive, "
            f"got {per_feature_ceiling!r}. Budget enforcement requires a positive ceiling."
        )

    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0

    if cost > 0.0:
        return cost

    threshold = _read_threshold()
    telemetry_lost = work_events > threshold

    if not telemetry_lost:
        return 0.0

    # Telemetry was lost: charge per-feature ceiling and emit structured event.
    logger.warning(
        "cost_telemetry_lost: feature_id=%s work_events=%d exit_code=%s "
        "attempt=%d applied_pessimistic_cost=%.4f — "
        "reported cost was 0 but work_events > threshold (%d); "
        "applying per-feature ceiling to preserve budget enforcement.",
        feature_id,
        work_events,
        exit_code,
        attempt_number,
        per_feature_ceiling,
        threshold,
    )
    return float(per_feature_ceiling)


def detect_cost_telemetry_loss(
    reported_cost: float | None,
    work_events: int,
) -> TelemetryLossResult:
    """Detect whether stream-json cost telemetry was lost during a sub-agent run.

    When a sub-agent crashes mid-work the stream-json parser may fail to deliver
    cost-delta events, leaving reported_cost==0.  This function distinguishes
    between three cases:

    - cost > 0 → normal, telemetry intact.
    - cost==0 AND work_events == 0 → genuine spawn-crash (free-retry path).
    - cost==0 AND work_events > threshold → telemetry LOST (UNKNOWN-but-nonzero).

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None coerced to 0.0.
        Negative values treated as 0.0.
    work_events:
        Count of substantive progress events from progress.jsonl.

    Returns
    -------
    TelemetryLossResult
        ``.telemetry_lost`` — True when cost==0 AND work_events > threshold.
        ``.effective_cost`` — reported cost (0.0 for lost/free-retry, positive
        value as-is when telemetry is intact). Use :func:`apply_budget_safety_net`
        to convert effective_cost to the pessimistic ceiling when telemetry_lost.
    """
    cost = float(reported_cost) if reported_cost is not None else 0.0
    if cost < 0.0:
        cost = 0.0

    if cost > 0.0:
        return TelemetryLossResult(telemetry_lost=False, effective_cost=cost)

    threshold = _read_threshold()
    telemetry_lost = work_events > threshold
    return TelemetryLossResult(telemetry_lost=telemetry_lost, effective_cost=0.0)


def apply_budget_safety_net(
    reported_cost: float | None,
    work_events: int,
    per_feature_ceiling: float,
    feature_id: str,
    exit_code: int | None = None,
    attempt_number: int = 1,
) -> float:
    """Apply the budget safety net: zero-reported-cost MUST NOT disable enforcement.

    When :func:`detect_cost_telemetry_loss` indicates telemetry was lost
    (cost==0 AND work_events > threshold), this function charges the
    per-feature ceiling as a pessimistic cost and emits a structured
    ``cost_telemetry_lost`` WARN log event.

    This is the safety net that must fire instead of the old "disable
    enforcement on zero cost" behaviour.  It delegates to
    :func:`enforce_cost_ceiling` which implements the canonical decision tree.

    Parameters
    ----------
    reported_cost:
        Raw cost from the SDK (total_cost_usd). None coerced to 0.0.
        Negative values treated as 0.0.
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
    float
        Effective cost to charge against the budget:
        - ``per_feature_ceiling`` when telemetry is lost (cost==0 and
          work_events > threshold).
        - 0.0 when it is a genuine free-retry spawn crash (cost==0 and
          work_events == 0).
        - The raw reported_cost otherwise.

    Raises
    ------
    ValueError
        When ``per_feature_ceiling`` is <= 0.
    """
    return enforce_cost_ceiling(
        reported_cost=reported_cost,
        work_events=work_events,
        per_feature_ceiling=per_feature_ceiling,
        feature_id=feature_id,
        exit_code=exit_code,
        attempt_number=attempt_number,
    )
