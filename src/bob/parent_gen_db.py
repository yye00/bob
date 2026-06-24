"""Public API for parent-generation DB inheritance at seed time (F-R7-422).

Provides two functions consumed by ``spawn_next_generation.sh`` and the
orchestrator bootstrap to propagate provenance across generation boundaries:

- :func:`read_parent_features` — query completed/needs_human/regression rows
  from the parent DB, indexed by ``spec_slot``.
- :func:`stamp_child_row` — write ``parent_status``, ``parent_completed_at``,
  and ``parent_evidence_hash`` onto a matched child feature row.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sqlite3
from datetime import datetime
from typing import TypedDict

logger = logging.getLogger(__name__)

_INHERITED_STATUSES = frozenset({"completed", "needs_human", "regression"})


class ParentFeatureRow(TypedDict):
    id: str
    spec_slot: str
    status: str
    updated_at: str | None
    evidence_hash: str | None


def read_parent_features(
    parent_db_path: str | pathlib.Path,
) -> dict[str, ParentFeatureRow]:
    """Return qualifying parent features indexed by ``spec_slot``.

    Reads every feature row from *parent_db_path* whose ``status`` is in
    ``{'completed', 'needs_human', 'regression'}`` and whose ``spec_slot``
    is non-NULL.  For each row the latest ``is_current=1`` evidence artifact
    is fetched and its SHA-256 pre-computed.

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.  If the file does not
            exist, returns an empty dict (first-gen seed scenario).

    Returns:
        ``{spec_slot: ParentFeatureRow}`` mapping.  Empty when the parent DB
        is absent or contains no qualifying rows.
    """
    parent_db_path = pathlib.Path(parent_db_path)
    if not parent_db_path.exists():
        logger.debug("Parent DB not found (first-gen?): %s", parent_db_path)
        return {}

    conn = sqlite3.connect(str(parent_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        placeholders = ",".join("?" for _ in _INHERITED_STATUSES)
        rows = conn.execute(
            f"SELECT id, spec_slot, status, updated_at FROM features "
            f"WHERE status IN ({placeholders}) AND spec_slot IS NOT NULL",
            list(_INHERITED_STATUSES),
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, ParentFeatureRow] = {}
    for row in rows:
        slot = row["spec_slot"]
        evidence_hash = _fetch_evidence_hash(parent_db_path, row["id"])
        result[slot] = ParentFeatureRow(
            id=row["id"],
            spec_slot=slot,
            status=row["status"],
            updated_at=row["updated_at"],
            evidence_hash=evidence_hash,
        )
    return result


def stamp_child_row(
    *,
    child_db_path: str | pathlib.Path,
    feature_id: str,
    parent_status: str,
    parent_completed_at: str | None,
    parent_evidence_hash: str | None,
) -> None:
    """Atomically stamp a child feature row with parent-generation provenance.

    Writes ``parent_status``, ``parent_completed_at``, and
    ``parent_evidence_hash`` in a single UPDATE inside a WAL-mode transaction.

    Args:
        child_db_path:        Path to bob_(N+1)'s ``bob.db``.
        feature_id:           UUID primary key of the child feature row.
        parent_status:        Status copied from the parent feature row.
        parent_completed_at:  ``updated_at`` timestamp from the parent row.
        parent_evidence_hash: SHA-256 of the parent's latest evidence artifact.
    """
    child_db_path = pathlib.Path(child_db_path)
    conn = sqlite3.connect(str(child_db_path), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute(
            """UPDATE features
               SET parent_status = ?,
                   parent_completed_at = ?,
                   parent_evidence_hash = ?,
                   updated_at = ?
               WHERE id = ?""",
            (
                parent_status,
                parent_completed_at,
                parent_evidence_hash,
                datetime.now().isoformat(),
                feature_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.debug(
        "stamp_child_row: feature=%s parent_status=%s hash=%s",
        feature_id[:8],
        parent_status,
        (parent_evidence_hash or "")[:16],
    )


def inherit_parent_status(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path,
) -> int:
    """Stamp child features with provenance from the parent DB at seed time.

    When ``spawn_next_generation.sh`` seeds bob_(N+1), call this to propagate
    completed/needs_human/regression status across generation boundaries.  For
    every child feature whose ``spec_slot`` matches a qualifying parent row,
    writes ``parent_status``, ``parent_completed_at``, and
    ``parent_evidence_hash``.

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob.db``.

    Returns:
        Number of child rows stamped.

    Raises:
        FileNotFoundError: If either DB path does not exist.
        ValueError: If ``parent_db_path`` is None or empty.
    """
    parent_features = read_parent_features(parent_db_path)
    if not parent_features:
        return 0

    child_db_path = pathlib.Path(child_db_path)

    child_conn = sqlite3.connect(str(child_db_path), timeout=30)
    child_conn.row_factory = sqlite3.Row
    child_conn.execute("PRAGMA journal_mode = WAL")
    child_conn.execute("PRAGMA busy_timeout = 30000")
    try:
        child_rows = child_conn.execute(
            "SELECT id, spec_slot FROM features WHERE spec_slot IS NOT NULL"
        ).fetchall()

        stamped = 0
        for child_row in child_rows:
            slot = child_row["spec_slot"]
            parent = parent_features.get(slot)
            if parent is None:
                continue

            child_conn.execute(
                """UPDATE features
                   SET parent_status = ?,
                       parent_completed_at = ?,
                       parent_evidence_hash = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (
                    parent["status"],
                    parent["updated_at"],
                    parent["evidence_hash"],
                    datetime.now().isoformat(),
                    child_row["id"],
                ),
            )
            logger.info(
                "inherit_parent_status: stamped feature %s (slot=%s) parent_status=%s",
                child_row["id"][:8],
                slot,
                parent["status"],
            )
            stamped += 1

        child_conn.commit()
    except Exception:
        child_conn.rollback()
        raise
    finally:
        child_conn.close()

    logger.info("inherit_parent_status: stamped=%d", stamped)
    return stamped


def inherit_parent_metadata(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path,
) -> int:
    """Alias for :func:`inherit_parent_status` — satisfies the inherit_parent_metadata AC.

    When ``spawn_next_generation.sh`` seeds bob_(N+1), propagate
    completed/needs_human/regression provenance from bob_N's DB.

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob.db``.

    Returns:
        Number of child rows stamped.
    """
    return inherit_parent_status(
        parent_db_path=parent_db_path,
        child_db_path=child_db_path,
    )


def _fetch_evidence_hash(
    db_path: pathlib.Path,
    feature_id: str,
) -> str | None:
    """Return SHA-256 of the most-recent current evidence artifact, or None."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        row = conn.execute(
            """SELECT content FROM evidence_artifacts
               WHERE feature_id = ? AND is_current = 1
               ORDER BY created_at DESC LIMIT 1""",
            (feature_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    content = row[0] or ""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
