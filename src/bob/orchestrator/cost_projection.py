"""F-R6-307: Pre-spawn cost projection gate.

Round 5 burned $29 with zero shipped features because each sub-agent
retry costs ~$0.70 regardless of success odds, and the orchestrator
had no pre-spawn projection check. It would grind to the cap, spawning
attempt after attempt until the budget was exhausted.

This module provides two pure functions that the orchestrator calls
*before* spawning a sub-agent for a feature:

1. :func:`project_feature_cost` queries historical ``sub_agent_runs``
   for runs against features in the same coarse "shape" bucket (task
   count + description-token-count) and returns p50 / p75 / p95 cost
   percentiles plus a recommended estimate.

2. :func:`allow_spawn` adds that estimate to the project's already-
   committed spend and to a count of in-flight ("running" / "executing")
   sub-agent runs, then refuses the spawn if the projected total would
   blow past ``headroom_factor * cap_usd``.

Design notes
------------

* Module is importable without side effects (no DB writes, no network).
* Takes a ``sqlite3.Connection`` from the caller — never opens its own.
* The default fallback estimate when history is thin is intentionally
  conservative (1.5 USD per attempt). Picking a high default would
  defeat the gate by making it always pass.
* The ``headroom_factor`` defaults to 0.95 and is clamped to that ceiling
  so a future caller cannot quietly raise it to 1.0 and disable the
  gate.
* Outstanding reservations are taken from ``sub_agent_runs`` rows whose
  status is in {'running', 'executing', 'queued'}. The original spec
  also mentioned an F-R6-201 ``cost_reservation`` table; that table does
  not exist in the current schema, so we fall back to sub_agent_runs
  only. The query degrades gracefully (returns 0 reservations) if the
  table is missing or the schema is unexpected.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Mapping

logger = logging.getLogger(__name__)


# Conservative fallback when we don't have enough history to estimate.
# Picked to be high enough to gate the *first* spawn on a tight budget,
# but low enough that it does not single-handedly trip the headroom on a
# normal-sized project. DO NOT raise this without thinking about whether
# you're disabling the gate.
DEFAULT_FALLBACK_ESTIMATE_USD = 1.5

# Minimum number of historical samples we want before trusting the
# bucket-specific p75. Below this we fall back to the conservative
# default above so a single outlier can't dominate the projection.
MIN_SAMPLES_FOR_BUCKET_ESTIMATE = 3

# Statuses that we count as "in flight" for the purpose of reserving
# their (still-unbilled) cost against the budget headroom. We deliberately
# include 'queued' even though current orchestrator code only writes
# 'running'/'executing' — future orchestrators may add a queued state and
# we'd rather over-count reservations than under-count.
IN_FLIGHT_STATUSES: tuple[str, ...] = ("running", "executing", "queued")

# Hard ceiling on headroom_factor. The whole point of this gate is to
# leave SOME breathing room under the cap. If a caller passes 1.0 (or
# higher) we silently clamp to this value so the gate keeps working.
MAX_HEADROOM_FACTOR = 0.95


def _feature_get(feature: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    """Pull a field from either a dict-like or an object-like feature."""

    if isinstance(feature, Mapping):
        return feature.get(key, default)
    return getattr(feature, key, default)


def _task_bucket(task_count: int | None) -> str:
    """Bucket features by task count so similar-shaped features compare.

    Buckets are coarse on purpose — we want enough samples per bucket
    to compute a stable p75, not statistical purity.
    """

    if task_count is None or task_count <= 0:
        return "unknown"
    if task_count <= 3:
        return "tiny"
    if task_count <= 8:
        return "small"
    if task_count <= 20:
        return "medium"
    return "large"


def _description_bucket(description: str | None) -> str:
    """Bucket features by description "token" count (whitespace-split)."""

    if not description:
        return "none"
    tokens = len(description.split())
    if tokens < 50:
        return "short"
    if tokens < 200:
        return "medium"
    return "long"


def _bucket_key(feature: Mapping[str, Any] | Any) -> tuple[str, str]:
    task_count = _feature_get(feature, "tasks_total")
    if task_count is None:
        task_count = _feature_get(feature, "task_count")
    description = _feature_get(feature, "description")
    return (_task_bucket(task_count), _description_bucket(description))


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile on a pre-sorted ascending list.

    ``pct`` is a fraction in [0, 1]. Returns 0.0 for an empty list so
    callers don't have to special-case it.
    """

    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pct = max(0.0, min(1.0, pct))
    idx = pct * (len(sorted_values) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _gather_historical_costs(
    db_conn: sqlite3.Connection,
    feature: Mapping[str, Any] | Any,
) -> list[float]:
    """Return historical costs (USD) for features in the same bucket.

    Joins ``sub_agent_runs`` to ``features`` on ``target_id`` to filter
    by task count / description size. Only completed runs with a positive
    recorded cost are included — failed and in-flight runs would skew
    the projection (failures often cost less, in-flight rows have no
    final cost yet).
    """

    target_bucket = _bucket_key(feature)
    try:
        cur = db_conn.execute(
            """
            SELECT sar.cost_usd, f.tasks_total, f.description
              FROM sub_agent_runs AS sar
              JOIN features AS f ON sar.target_id = f.id
             WHERE sar.target_type = 'feature'
               AND sar.cost_usd IS NOT NULL
               AND sar.cost_usd > 0
               AND sar.status = 'completed'
            """
        )
        rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.warning("cost_projection: history query failed (%s); using fallback", exc)
        return []

    costs: list[float] = []
    for cost_usd, tasks_total, description in rows:
        bucket = (_task_bucket(tasks_total), _description_bucket(description))
        if bucket == target_bucket:
            try:
                costs.append(float(cost_usd))
            except (TypeError, ValueError):
                continue
    return costs


def project_feature_cost(
    db_conn: sqlite3.Connection,
    feature: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Project the cost of a single sub-agent spawn for ``feature``.

    Returns a dict with:
        - ``p50_usd``, ``p75_usd``, ``p95_usd``: percentile costs from
          historical bucket-matched runs (0.0 when no history).
        - ``n_samples``: number of historical runs that fed the percentiles.
        - ``estimate_used``: the single number callers should add to
          ``committed_spend``. Defaults to ``p75`` when we have at least
          :data:`MIN_SAMPLES_FOR_BUCKET_ESTIMATE` samples, otherwise
          :data:`DEFAULT_FALLBACK_ESTIMATE_USD`.
        - ``source``: 'history' or 'fallback' so callers can log /
          reason about which path produced the estimate.
    """

    costs = _gather_historical_costs(db_conn, feature)
    n_samples = len(costs)
    costs_sorted = sorted(costs)

    p50 = _percentile(costs_sorted, 0.50)
    p75 = _percentile(costs_sorted, 0.75)
    p95 = _percentile(costs_sorted, 0.95)

    if n_samples >= MIN_SAMPLES_FOR_BUCKET_ESTIMATE:
        estimate = p75
        source = "history"
    else:
        estimate = DEFAULT_FALLBACK_ESTIMATE_USD
        source = "fallback"

    return {
        "p50_usd": p50,
        "p75_usd": p75,
        "p95_usd": p95,
        "n_samples": n_samples,
        "estimate_used": estimate,
        "source": source,
    }


def _outstanding_reservations_usd(
    db_conn: sqlite3.Connection,
    feature: Mapping[str, Any] | Any,
) -> tuple[float, int]:
    """Return (total_reserved_usd, count) of in-flight sub-agent runs.

    For each in-flight row we use its recorded ``cost_usd`` if present
    (some orchestrators stream partial cost while a run is executing),
    otherwise we charge it the same per-feature estimate that
    :func:`project_feature_cost` would use — so an idle gate can't be
    fooled by a fleet of just-started sub-agents whose ``cost_usd``
    columns are still NULL.
    """

    placeholders = ",".join("?" * len(IN_FLIGHT_STATUSES))
    try:
        cur = db_conn.execute(
            f"""
            SELECT cost_usd
              FROM sub_agent_runs
             WHERE status IN ({placeholders})
            """,
            IN_FLIGHT_STATUSES,
        )
        rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.warning("cost_projection: reservation query failed (%s); assuming 0", exc)
        return 0.0, 0

    if not rows:
        return 0.0, 0

    # Estimate per-feature cost once, in case any in-flight row has a
    # NULL cost_usd we need to fill in. This intentionally re-uses the
    # *same feature's* bucket — we don't know the bucket of the in-flight
    # row's target without a join, and using the current feature's bucket
    # is a conservative-enough proxy for a budget gate.
    projection = project_feature_cost(db_conn, feature)
    per_run_estimate = float(projection["estimate_used"])

    total = 0.0
    for (cost_usd,) in rows:
        if cost_usd is None or cost_usd <= 0:
            total += per_run_estimate
        else:
            try:
                total += float(cost_usd)
            except (TypeError, ValueError):
                total += per_run_estimate
    return total, len(rows)


def allow_spawn(
    db_conn: sqlite3.Connection,
    feature: Mapping[str, Any] | Any,
    committed_spend_usd: float,
    cap_usd: float | None,
    headroom_factor: float = 0.95,
) -> tuple[bool, dict[str, Any]]:
    """Decide whether to spawn a sub-agent for ``feature``.

    Args:
        db_conn: open sqlite3 connection (not closed by this function).
        feature: dict or Feature with at least ``tasks_total`` and
            ``description`` fields (both optional — missing fields just
            map to the "unknown" bucket).
        committed_spend_usd: how much the project has already billed.
        cap_usd: total budget ceiling. ``None`` or a non-positive value
            means "no cap" and the gate always allows the spawn.
        headroom_factor: fraction of the cap we're willing to project
            into. Clamped to :data:`MAX_HEADROOM_FACTOR`.

    Returns:
        ``(allowed, info)`` where ``info`` includes the projected total,
        the estimate used, outstanding reservations, the effective
        ceiling, and a human-readable ``reason``.
    """

    if cap_usd is None or cap_usd <= 0:
        return True, {
            "projected_total_usd": float(committed_spend_usd),
            "estimate_used": 0.0,
            "outstanding_reservations_usd": 0.0,
            "outstanding_reservations_count": 0,
            "effective_ceiling_usd": float("inf"),
            "headroom_factor": headroom_factor,
            "n_samples": 0,
            "source": "no-cap",
            "reason": "no cost cap configured",
        }

    # Clamp headroom so a caller can't silently disable the gate.
    effective_headroom = min(float(headroom_factor), MAX_HEADROOM_FACTOR)
    effective_headroom = max(0.0, effective_headroom)
    ceiling = effective_headroom * float(cap_usd)

    projection = project_feature_cost(db_conn, feature)
    estimate = float(projection["estimate_used"])
    reserved, reserved_count = _outstanding_reservations_usd(db_conn, feature)

    projected_total = float(committed_spend_usd) + reserved + estimate
    remaining = ceiling - float(committed_spend_usd) - reserved

    info = {
        "projected_total_usd": projected_total,
        "estimate_used": estimate,
        "outstanding_reservations_usd": reserved,
        "outstanding_reservations_count": reserved_count,
        "effective_ceiling_usd": ceiling,
        "headroom_factor": effective_headroom,
        "n_samples": int(projection["n_samples"]),
        "source": projection["source"],
        "p50_usd": projection["p50_usd"],
        "p75_usd": projection["p75_usd"],
        "p95_usd": projection["p95_usd"],
    }

    if projected_total <= ceiling:
        info["reason"] = (
            f"projection ${projected_total:.2f} <= ceiling ${ceiling:.2f} "
            f"(estimate ${estimate:.2f}, reserved ${reserved:.2f}, "
            f"source={projection['source']}, n={projection['n_samples']})"
        )
        return True, info

    info["reason"] = (
        f"cost-cap projection (${projected_total:.2f} projected, "
        f"${max(remaining, 0.0):.2f} remaining under "
        f"{effective_headroom:.0%} of ${float(cap_usd):.2f} cap; "
        f"estimate ${estimate:.2f}, reserved ${reserved:.2f} across "
        f"{reserved_count} in-flight runs, source={projection['source']}, "
        f"n={projection['n_samples']})"
    )
    return False, info


def project_spawn_cost(
    db_conn: sqlite3.Connection,
    feature: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Alias for :func:`project_feature_cost` (acceptance-criteria name)."""
    return project_feature_cost(db_conn, feature)


def should_spawn(
    db_conn: sqlite3.Connection,
    feature: Mapping[str, Any] | Any,
    committed_spend_usd: float,
    cap_usd: float | None,
    headroom_factor: float = 0.95,
) -> tuple[bool, dict[str, Any]]:
    """Alias for :func:`allow_spawn` (acceptance-criteria name)."""
    return allow_spawn(db_conn, feature, committed_spend_usd, cap_usd, headroom_factor)


__all__ = [
    "project_feature_cost",
    "project_spawn_cost",
    "allow_spawn",
    "should_spawn",
    "DEFAULT_FALLBACK_ESTIMATE_USD",
    "MIN_SAMPLES_FOR_BUCKET_ESTIMATE",
    "MAX_HEADROOM_FACTOR",
    "IN_FLIGHT_STATUSES",
]
