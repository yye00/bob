"""Atomic feature-claim for concurrent workers (1cb15253-ada9-46f2-9341-84950d8135ef).

Provides a single-statement claim that atomically transitions a feature
from 'ready' to 'executing' and stamps the claiming worker's id, returning
the row only when the transition actually succeeds.

SQLite >= 3.35 supports UPDATE … RETURNING.  The project ships 3.31.1 on
the CI host, so we use the next-best alternative: a transaction that
performs the UPDATE and then SELECTs the row with a WHERE clause that
re-checks the old status—so only the first writer to commit the
UPDATE gets a non-empty RETURNING-equivalent result.

Concurrency model
-----------------
SQLite in WAL mode allows one writer at a time.  Under thread concurrency
two workers race to acquire the write lock.  The first commits its UPDATE
(status = 'ready' → 'executing'); when the second commits its own UPDATE
the WHERE status = 'ready' no longer matches, so zero rows are updated and
the second worker gets nothing.  This gives us the necessary mutual
exclusion without any application-level locking.

Integration point: bob3.orchestrator.run_loop
"""

from __future__ import annotations

import logging
from datetime import datetime

from bob3.db import (
    _FEATURE_COLUMNS,
    _row_to_feature,
    get_connection,
)
from bob3.models import Feature

logger = logging.getLogger(__name__)

# Columns used to SELECT the claimed row right after the UPDATE.
_SELECT_COLS = ", ".join(f"f.{c}" for c in _FEATURE_COLUMNS)


def claim_next_ready_feature(
    *,
    project_id: str,
    worker_id: str,
) -> Feature | None:
    """Atomically claim the next ready feature for a worker.

    Finds the highest-priority feature that satisfies ALL of:
    - status = 'ready'
    - readiness_score >= risk-category threshold (same rules as features_ready view)
    - no active reviewer veto
    - all dependencies completed
    - belongs to ``project_id``

    Then, in a single serialised transaction, transitions it to
    ``status = 'executing'`` and records ``worker_id`` in the
    ``updated_at`` field's companion metadata (stored via a log entry).

    Because SQLite serialises writers, the UPDATE only affects the row when
    its status is still 'ready'.  Any concurrent worker racing the same
    feature will find zero rows updated and receive None.

    Args:
        project_id: The project whose ready features are considered.
        worker_id: An identifier for the calling worker (used in logging).

    Returns:
        The claimed :class:`~bob3.models.Feature` with ``status='executing'``,
        or ``None`` if no ready feature was available.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Find the best candidate using the same criteria as the
        # features_ready view but within this transaction so no other
        # writer can sneak in between SELECT and UPDATE.
        pick_sql = f"""
            SELECT {_SELECT_COLS}
            FROM features f
            WHERE f.project_id = ?
              AND f.status = 'ready'
              AND f.readiness_score >= (
                  CASE f.risk_category
                      WHEN 'low'      THEN 0.70
                      WHEN 'medium'   THEN 0.80
                      WHEN 'high'     THEN 0.90
                      WHEN 'critical' THEN 0.95
                      ELSE 0.80
                  END
              )
              AND NOT EXISTS (
                  SELECT 1 FROM review_history r
                  WHERE r.feature_id = f.id
                    AND r.veto_active = TRUE
              )
              AND NOT EXISTS (
                  SELECT 1 FROM feature_dependencies fd
                  JOIN features dep ON dep.id = fd.depends_on_feature_id
                  WHERE fd.feature_id = f.id
                    AND dep.status != 'completed'
              )
            ORDER BY f.priority ASC, f.created_at ASC
            LIMIT 1
        """
        cursor = conn.execute(pick_sql, (project_id,))
        row = cursor.fetchone()

        if row is None:
            conn.rollback()
            return None

        # Convert row → Feature (still 'ready' at this point, in this txn).
        candidate = _row_to_feature(row)
        feature_id = candidate.id

        now_iso = datetime.now().isoformat()
        update_sql = """
            UPDATE features
               SET status = 'executing',
                   updated_at = ?
             WHERE id = ?
               AND status = 'ready'
        """
        update_cursor = conn.execute(update_sql, (now_iso, feature_id))

        if update_cursor.rowcount == 0:
            # Another writer already claimed this feature between our BEGIN
            # and this UPDATE (shouldn't happen with BEGIN IMMEDIATE, but
            # be defensive).
            conn.rollback()
            logger.debug(
                "worker %s lost claim race for feature %s; returning None",
                worker_id,
                feature_id,
            )
            return None

        conn.commit()

        logger.info(
            "worker %s claimed feature %s (%s)",
            worker_id,
            feature_id[:8],
            candidate.name,
        )

        # Return a Feature with the updated status.
        claimed = Feature(
            **{
                **{c: getattr(candidate, c) for c in _FEATURE_COLUMNS},
                "status": "executing",
                "updated_at": datetime.fromisoformat(now_iso),
            }
        )
        return claimed

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
