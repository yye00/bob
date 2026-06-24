"""Parent-gen DB inheritance at seed time (82231bc5 — F-R7-400).

Public API consumed by spawn_next_generation.sh when seeding bob_(N+1).
Reads every completed/needs_human/regression feature row from bob_N's
bob.db, matches by spec_slot against the child DB's features, and stamps
parent_status, parent_completed_at, and parent_evidence_hash onto each
matched child row.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sqlite3
from datetime import datetime
from typing import NamedTuple

logger = logging.getLogger(__name__)

_QUALIFYING_STATUSES = frozenset({"completed", "needs_human", "regression"})


class ParentFeatureRow(NamedTuple):
    id: str
    spec_slot: str
    status: str
    updated_at: str | None
    evidence_hash: str | None


def read_parent_features(
    parent_db_path: str | pathlib.Path,
) -> dict[str, ParentFeatureRow]:
    """Return qualifying parent features indexed by spec_slot.

    Reads every feature row from parent_db_path whose status is in
    {'completed', 'needs_human', 'regression'} and whose spec_slot is
    non-NULL.  For each row the latest is_current=1 evidence artifact
    is fetched and its SHA-256 pre-computed.

    Args:
        parent_db_path: Path to bob_N's bob.db.

    Returns:
        {spec_slot: ParentFeatureRow} mapping. Empty when no qualifying rows.

    Raises:
        FileNotFoundError: If parent_db_path does not exist.
        ValueError: If parent_db_path is None or empty.
    """
    if parent_db_path is None:
        raise ValueError("parent_db_path must not be None")
    if str(parent_db_path) == "":
        raise ValueError("parent_db_path must not be an empty string")

    parent_db_path = pathlib.Path(parent_db_path)
    if not parent_db_path.exists():
        raise FileNotFoundError(f"Parent DB not found: {parent_db_path}")

    conn = sqlite3.connect(str(parent_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        placeholders = ",".join("?" for _ in _QUALIFYING_STATUSES)
        rows = conn.execute(
            f"SELECT id, spec_slot, status, updated_at FROM features "
            f"WHERE status IN ({placeholders}) AND spec_slot IS NOT NULL",
            list(_QUALIFYING_STATUSES),
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

    Writes parent_status, parent_completed_at, and parent_evidence_hash
    in a single UPDATE inside a WAL-mode transaction.

    Args:
        child_db_path:        Path to bob_(N+1)'s bob.db.
        feature_id:           UUID primary key of the child feature row.
        parent_status:        Status copied from the parent feature row.
        parent_completed_at:  updated_at timestamp from the parent row.
        parent_evidence_hash: SHA-256 of the parent's latest evidence artifact.

    Raises:
        FileNotFoundError: If child_db_path does not exist.
        ValueError: If feature_id or parent_status is empty/None.
    """
    if not feature_id:
        raise ValueError("feature_id must not be empty")
    if not parent_status:
        raise ValueError("parent_status must not be empty")

    child_db_path = pathlib.Path(child_db_path)
    if not child_db_path.exists():
        raise FileNotFoundError(f"Child DB not found: {child_db_path}")

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


class StampResult(NamedTuple):
    """Summary returned by :func:`stamp_parent_metadata`."""

    stamped: int
    skipped_no_slot: int
    skipped_no_parent_match: int


def stamp_parent_metadata(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path | None = None,
) -> StampResult:
    """Stamp child-generation features with provenance from the parent DB at seed time.

    When spawn_next_generation.sh seeds bob_(N+1), call this function to
    propagate completed/needs_human/regression status across generation
    boundaries. For every child feature whose spec_slot matches a qualifying
    parent row, writes parent_status, parent_completed_at, and
    parent_evidence_hash.

    Args:
        parent_db_path: Path to bob_N's bob.db.
        child_db_path:  Path to bob_(N+1)'s bob.db. Defaults to the
                        BOB_DATABASE_PATH env var or bob.db in cwd.

    Returns:
        StampResult with counts of rows stamped / skipped.

    Raises:
        FileNotFoundError: If either DB path does not exist.
        ValueError: If parent_db_path is None or otherwise invalid.
    """
    if parent_db_path is None:
        raise ValueError("parent_db_path must not be None")
    if str(parent_db_path) == "":
        raise ValueError("parent_db_path must not be an empty string")

    parent_db_path = pathlib.Path(parent_db_path)

    if child_db_path is None:
        import os
        env_path = os.environ.get("BOB_DATABASE_PATH")
        child_db_path = pathlib.Path(env_path) if env_path else pathlib.Path("bob.db")
    else:
        child_db_path = pathlib.Path(child_db_path)

    if not parent_db_path.exists():
        raise FileNotFoundError(f"Parent DB not found: {parent_db_path}")
    if not child_db_path.exists():
        raise FileNotFoundError(f"Child DB not found: {child_db_path}")

    parent_by_slot = read_parent_features(parent_db_path)

    conn = sqlite3.connect(str(child_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        child_rows = conn.execute("SELECT id, spec_slot FROM features").fetchall()
    finally:
        conn.close()

    stamped = 0
    skipped_no_slot = 0
    skipped_no_parent_match = 0

    for child in child_rows:
        slot = child["spec_slot"]
        if not slot:
            skipped_no_slot += 1
            continue

        parent = parent_by_slot.get(slot)
        if parent is None:
            skipped_no_parent_match += 1
            continue

        stamp_child_row(
            child_db_path=child_db_path,
            feature_id=child["id"],
            parent_status=parent.status,
            parent_completed_at=parent.updated_at,
            parent_evidence_hash=parent.evidence_hash,
        )
        logger.info(
            "stamp_parent_metadata: stamped feature %s (slot=%s) parent_status=%s",
            child["id"][:8],
            slot,
            parent.status,
        )
        stamped += 1

    logger.info(
        "stamp_parent_metadata: stamped=%d skipped_no_slot=%d skipped_no_parent_match=%d",
        stamped,
        skipped_no_slot,
        skipped_no_parent_match,
    )
    return StampResult(
        stamped=stamped,
        skipped_no_slot=skipped_no_slot,
        skipped_no_parent_match=skipped_no_parent_match,
    )


def inherit_parent_metadata(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path | None = None,
) -> StampResult:
    """Alias for :func:`stamp_parent_metadata` — satisfies the inherit_parent_metadata AC.

    When spawn_next_generation.sh seeds bob_(N+1), call this function to
    propagate completed/needs_human/regression provenance from bob_N's DB into
    the new generation's feature rows.

    Args:
        parent_db_path: Path to bob_N's bob.db.
        child_db_path:  Path to bob_(N+1)'s bob.db. Defaults to the
                        BOB_DATABASE_PATH env var or bob.db in cwd.

    Returns:
        StampResult with counts of rows stamped / skipped.

    Raises:
        FileNotFoundError: If either DB path does not exist.
        ValueError: If parent_db_path is None or otherwise invalid.
    """
    return stamp_parent_metadata(
        parent_db_path=parent_db_path,
        child_db_path=child_db_path,
    )


def inherit_parent_status(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path | None = None,
) -> StampResult:
    """Alias for :func:`stamp_parent_metadata` — satisfies the inherit_parent_status AC (F-R7-422).

    When spawn_next_generation.sh seeds bob_(N+1), call this function to
    propagate completed/needs_human/regression provenance from bob_N's DB into
    the new generation's feature rows.

    Args:
        parent_db_path: Path to bob_N's bob.db.
        child_db_path:  Path to bob_(N+1)'s bob.db. Defaults to the
                        BOB_DATABASE_PATH env var or bob.db in cwd.

    Returns:
        StampResult with counts of rows stamped / skipped.

    Raises:
        FileNotFoundError: If either DB path does not exist.
        ValueError: If parent_db_path is None or otherwise invalid.
    """
    return stamp_parent_metadata(
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


# Alias satisfying the read_completed_features AC (F-R7-400 / 24bef040)
read_completed_features = read_parent_features
