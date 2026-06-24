"""Per-feature cost reservation and concurrent budget guard (feature 7841fb76).

Solves the race condition where N concurrent workers each read the running
total once, all pass the budget guard, and collectively overshoot max_cost
by N feature-budgets.

The reservation model works as follows:

1. Before a worker claims a feature it calls :func:`reserve_budget`, which
   atomically inserts a row into ``cost_reservations`` iff
   ``committed_spend + outstanding_reservations + estimate <= cap``.

2. On feature completion (success or failure) the worker calls
   :func:`release_reservation`, which removes the reservation row.  If the
   feature succeeded the caller records the actual cost via the normal
   ``db.update_project_cost`` path; the reservation was only a forward-hold.

3. The estimated budget defaults to the historical p75 cost per feature in
   the same task/description bucket, sourced from
   :mod:`bob.orchestrator.cost_projection` (the F-R6-307 estimator).

Design constraints
------------------
* SQLite is the only dependency — no external locking primitives.
* The CHECK is done inside a single ``BEGIN IMMEDIATE`` transaction so the
  read-then-insert is atomic even with concurrent writers.
* The table is created lazily on first use; callers never need to call an
  init function.
* The module is importable without side effects.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from typing import Any, Mapping

from bob.orchestrator.cost_projection import project_feature_cost

logger = logging.getLogger(__name__)

# DDL for the reservation table.  Created lazily on first use so the module
# can be imported without a live database.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cost_reservations (
    id           TEXT PRIMARY KEY,
    feature_id   TEXT NOT NULL,
    project_id   TEXT NOT NULL,
    estimate_usd REAL NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Index so "sum of outstanding reservations for a project" is fast.
_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cost_reservations_project
    ON cost_reservations (project_id);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create the reservation table and index if they do not exist."""
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_INDEX_SQL)


def _outstanding_reserved_usd(
    conn: sqlite3.Connection,
    project_id: str,
) -> float:
    """Sum of all outstanding reservation amounts for *project_id*."""
    cur = conn.execute(
        "SELECT COALESCE(SUM(estimate_usd), 0.0) FROM cost_reservations WHERE project_id = ?",
        (project_id,),
    )
    row = cur.fetchone()
    return float(row[0]) if row else 0.0


def reserve_budget(
    conn: sqlite3.Connection,
    *,
    feature: Mapping[str, Any] | Any,
    project_id: str,
    committed_spend_usd: float,
    cap_usd: float | None,
    headroom_factor: float = 0.95,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Atomically reserve an estimated budget slot for *feature*.

    The reservation succeeds only if::

        committed_spend + outstanding_reservations + estimate <= effective_cap

    where ``effective_cap = min(headroom_factor, 0.95) * cap_usd``.

    Args:
        conn: Open sqlite3 connection.  The function begins its own
            ``IMMEDIATE`` transaction; do **not** call this inside an
            existing write transaction.
        feature: Dict-like or object with at least ``id``, ``tasks_total``
            and ``description`` fields.  Missing fields map to the "unknown"
            bucket in the cost estimator.
        project_id: The bob project this feature belongs to.
        committed_spend_usd: Already-billed cost for the project.
        cap_usd: Total budget ceiling.  ``None`` or ``<= 0`` means no cap
            and the reservation always succeeds (returning a nominal zero-
            cost slot).
        headroom_factor: Fraction of the cap that may be occupied.  Clamped
            to 0.95 so callers cannot silently disable the guard.

    Returns:
        ``(granted, reservation_id, info)`` where:

        * ``granted`` is ``True`` when the slot was reserved.
        * ``reservation_id`` is the UUID string of the new row (or ``None``
          when ``granted`` is ``False``).
        * ``info`` is a diagnostic dict with keys ``estimate_used``,
          ``outstanding_reservations_usd``, ``committed_spend_usd``,
          ``projected_total_usd``, ``effective_ceiling_usd``, and
          ``reason``.
    """
    def _feature_attr(key: str, default: Any = None) -> Any:
        if isinstance(feature, Mapping):
            return feature.get(key, default)
        return getattr(feature, key, default)

    feature_id = _feature_attr("id", "unknown")

    # No-cap fast path: grant unconditionally with a zero-cost reservation
    # so callers always get a reservation_id they can release later.
    if cap_usd is None or cap_usd <= 0:
        reservation_id = str(uuid.uuid4())
        try:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO cost_reservations (id, feature_id, project_id, estimate_usd) "
                "VALUES (?, ?, ?, ?)",
                (reservation_id, feature_id, project_id, 0.0),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.warning("reserve_budget: no-cap insert failed (%s); granting without DB row", exc)
            reservation_id = None
        info = {
            "estimate_used": 0.0,
            "outstanding_reservations_usd": 0.0,
            "committed_spend_usd": float(committed_spend_usd),
            "projected_total_usd": float(committed_spend_usd),
            "effective_ceiling_usd": float("inf"),
            "source": "no-cap",
            "reason": "no cost cap configured",
        }
        return True, reservation_id, info

    effective_headroom = max(0.0, min(float(headroom_factor), 0.95))
    effective_ceiling = effective_headroom * float(cap_usd)

    # Project cost for this feature.
    try:
        projection = project_feature_cost(conn, feature)
        estimate = float(projection["estimate_used"])
        source = projection["source"]
        n_samples = int(projection["n_samples"])
    except Exception as exc:
        logger.warning("reserve_budget: cost projection failed (%s); using fallback 1.5", exc)
        from bob.orchestrator.cost_projection import DEFAULT_FALLBACK_ESTIMATE_USD
        estimate = DEFAULT_FALLBACK_ESTIMATE_USD
        source = "fallback"
        n_samples = 0

    try:
        _ensure_table(conn)
        # BEGIN IMMEDIATE acquires a write lock before reading outstanding
        # reservations, so no two concurrent callers can both observe the same
        # (low) outstanding total and both decide to reserve.
        conn.execute("BEGIN IMMEDIATE")
        outstanding = _outstanding_reserved_usd(conn, project_id)
        projected_total = float(committed_spend_usd) + outstanding + estimate

        info: dict[str, Any] = {
            "estimate_used": estimate,
            "outstanding_reservations_usd": outstanding,
            "committed_spend_usd": float(committed_spend_usd),
            "projected_total_usd": projected_total,
            "effective_ceiling_usd": effective_ceiling,
            "source": source,
            "n_samples": n_samples,
        }

        if projected_total > effective_ceiling:
            conn.execute("ROLLBACK")
            remaining = max(0.0, effective_ceiling - float(committed_spend_usd) - outstanding)
            info["reason"] = (
                f"budget cap would be exceeded: projected ${projected_total:.2f} > "
                f"ceiling ${effective_ceiling:.2f} "
                f"(committed ${committed_spend_usd:.2f}, reserved ${outstanding:.2f}, "
                f"estimate ${estimate:.2f}, source={source}, n={n_samples}, "
                f"remaining ${remaining:.2f})"
            )
            return False, None, info

        reservation_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO cost_reservations (id, feature_id, project_id, estimate_usd) "
            "VALUES (?, ?, ?, ?)",
            (reservation_id, feature_id, project_id, estimate),
        )
        conn.commit()

        info["reason"] = (
            f"reservation granted: projected ${projected_total:.2f} <= "
            f"ceiling ${effective_ceiling:.2f} "
            f"(committed ${committed_spend_usd:.2f}, reserved ${outstanding:.2f}, "
            f"estimate ${estimate:.2f}, source={source}, n={n_samples})"
        )
        return True, reservation_id, info

    except sqlite3.Error as exc:
        logger.warning(
            "reserve_budget: DB error for feature %s (%s); granting conservatively",
            feature_id,
            exc,
        )
        # On DB error fall back to allowing the spawn — the downstream
        # budget_exceeded() check remains a backstop.
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        info = {
            "estimate_used": estimate,
            "outstanding_reservations_usd": 0.0,
            "committed_spend_usd": float(committed_spend_usd),
            "projected_total_usd": float(committed_spend_usd) + estimate,
            "effective_ceiling_usd": effective_ceiling,
            "source": "error-fallback",
            "n_samples": 0,
            "reason": f"DB error ({exc}); granted conservatively",
        }
        return True, None, info


def release_reservation(
    conn: sqlite3.Connection,
    reservation_id: str | None,
) -> bool:
    """Remove a reservation created by :func:`reserve_budget`.

    Should be called after a feature completes (success or failure) to free
    the budget slot.  The actual cost is recorded separately via
    ``db.update_project_cost``; this function only removes the forward-hold.

    Args:
        conn: Open sqlite3 connection.
        reservation_id: The string returned in the second element of the
            :func:`reserve_budget` result.  ``None`` is accepted silently
            (no-op) so callers do not need to special-case the no-cap or
            error-fallback paths.

    Returns:
        ``True`` if a row was deleted, ``False`` if the ID was not found or
        was ``None``.
    """
    if reservation_id is None:
        return False
    try:
        cur = conn.execute(
            "DELETE FROM cost_reservations WHERE id = ?",
            (reservation_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning("release_reservation: DELETE failed for %s (%s)", reservation_id, exc)
        return False


def outstanding_reservations(
    conn: sqlite3.Connection,
    project_id: str,
) -> tuple[float, int]:
    """Return ``(total_reserved_usd, count)`` for *project_id*.

    Convenience function for callers that want to inspect the outstanding
    reservation state without going through the full reservation flow.
    """
    try:
        _ensure_table(conn)
        cur = conn.execute(
            "SELECT COALESCE(SUM(estimate_usd), 0.0), COUNT(*) "
            "FROM cost_reservations WHERE project_id = ?",
            (project_id,),
        )
        row = cur.fetchone()
        if row:
            return float(row[0]), int(row[1])
        return 0.0, 0
    except sqlite3.Error as exc:
        logger.warning("outstanding_reservations: query failed (%s)", exc)
        return 0.0, 0


__all__ = [
    "reserve_budget",
    "release_reservation",
    "outstanding_reservations",
]
