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

Integration point: bob.orchestrator.run_loop
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from bob.db import (
    _FEATURE_COLUMNS,
    _row_to_feature,
    get_connection,
)
from bob.models import Feature

logger = logging.getLogger(__name__)

# Columns used to SELECT the claimed row right after the UPDATE.
_SELECT_COLS = ", ".join(f"f.{c}" for c in _FEATURE_COLUMNS)

# Environment variable that, when set to a float in [0,1], REPLACES the
# per-risk readiness thresholds with a single floor for all risk categories.
READINESS_THRESHOLD_ENV = "BOB_READINESS_THRESHOLD"

# Per-risk readiness floors used when no valid override is present. These
# mirror the features_ready view.
_PER_RISK_THRESHOLDS = {
    "low": 0.70,
    "medium": 0.80,
    "high": 0.90,
    "critical": 0.95,
}
_DEFAULT_THRESHOLD = 0.80


def parse_readiness_threshold(raw: str) -> float:
    """Strictly parse a readiness-threshold string into a float in [0, 1].

    Unlike :func:`resolve_readiness_override`, this does NOT silently swallow
    bad input — it is the error-path entry point.

    Raises:
        ValueError: If ``raw`` is not a string, is empty/whitespace-only,
            is not a finite number, or falls outside ``[0.0, 1.0]``.
    """
    if not isinstance(raw, str):
        raise ValueError(
            f"readiness threshold must be a string, got {type(raw).__name__}"
        )
    stripped = raw.strip()
    if not stripped:
        raise ValueError("readiness threshold is empty")
    try:
        value = float(stripped)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"readiness threshold {raw!r} is not a number") from exc
    # Reject NaN / inf — comparisons against them silently break gating.
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"readiness threshold {raw!r} is not finite")
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"readiness threshold {value} is out of range [0.0, 1.0]")
    return value


def resolve_readiness_override(env: dict | None = None) -> float | None:
    """Lazily resolve the optional readiness-threshold override from the env.

    This is the lenient claim-path resolver: an unset, empty, or malformed
    value returns ``None`` (fall back to the per-risk defaults) rather than
    raising. Valid values are within ``[0.0, 1.0]``.

    Args:
        env: Optional mapping to read from instead of ``os.environ`` (for
            testing). Defaults to ``os.environ``.

    Returns:
        A float in ``[0.0, 1.0]`` when a valid override is present, else
        ``None``.
    """
    source = os.environ if env is None else env
    raw = source.get(READINESS_THRESHOLD_ENV, "")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return parse_readiness_threshold(raw)
    except ValueError:
        return None


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
        The claimed :class:`~bob.models.Feature` with ``status='executing'``,
        or ``None`` if no ready feature was available.
    """
    conn = get_connection()
    # Optional global readiness-threshold override. When BOB_READINESS_THRESHOLD
    # is set to a float in [0,1], it REPLACES the per-risk thresholds with a
    # single floor. Use to recover from the F-R7-564 readiness deadlock where
    # spec_quality_score is absent (None) and readiness falls back to a low
    # AC-count heuristic, leaving genuinely-ready features below the 0.80 gate
    # and collapsing concurrency. Dependency gating is unaffected.
    _readiness_override = resolve_readiness_override()
    if _readiness_override is not None:
        _readiness_clause = f"AND f.readiness_score >= {_readiness_override}"
    else:
        _readiness_clause = """AND f.readiness_score >= (
                  CASE f.risk_category
                      WHEN 'low'      THEN 0.70
                      WHEN 'medium'   THEN 0.80
                      WHEN 'high'     THEN 0.90
                      WHEN 'critical' THEN 0.95
                      ELSE 0.80
                  END
              )"""
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
              {_readiness_clause}
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
