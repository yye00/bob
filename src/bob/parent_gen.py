"""Parent-gen DB inheritance at seed time (F-R7-400).

Public entry point consumed by ``spawn_next_generation.sh`` when seeding
bob_(N+1).  Reads every completed/needs_human/regression feature row from
bob_N's bob.db, matches by ``spec_slot`` against the child DB's features,
and stamps ``parent_status``, ``parent_completed_at``, and
``parent_evidence_hash`` onto each matched child row.
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

    When ``spawn_next_generation.sh`` seeds bob_(N+1), call this function to
    propagate completed/needs_human/regression status across generation
    boundaries.  For every child feature whose ``spec_slot`` matches a
    qualifying parent row, writes ``parent_status``, ``parent_completed_at``,
    and ``parent_evidence_hash``.

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob.db``.  Defaults to the
                        ``BOB_DATABASE_PATH`` env var or ``bob.db`` in cwd.

    Returns:
        :class:`StampResult` with counts of rows stamped / skipped.

    Raises:
        FileNotFoundError: If either DB path does not exist.
        ValueError: If ``parent_db_path`` is ``None`` or otherwise invalid.
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

    parent_by_slot = _load_parent_by_slot(parent_db_path)
    child_features = _load_child_features(child_db_path)

    stamped = 0
    skipped_no_slot = 0
    skipped_no_parent_match = 0

    child_conn = sqlite3.connect(str(child_db_path), timeout=30)
    child_conn.execute("PRAGMA journal_mode = WAL")
    child_conn.execute("PRAGMA busy_timeout = 30000")
    try:
        for child in child_features:
            slot = child.get("spec_slot")
            if not slot:
                skipped_no_slot += 1
                continue

            parent = parent_by_slot.get(slot)
            if parent is None:
                skipped_no_parent_match += 1
                continue

            evidence_hash = _fetch_evidence_hash(parent_db_path, parent["id"])

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
                    evidence_hash,
                    datetime.now().isoformat(),
                    child["id"],
                ),
            )
            logger.info(
                "stamp_parent_metadata: stamped feature %s (slot=%s) parent_status=%s",
                child["id"][:8],
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


def inherit_parent_status(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path | None = None,
) -> StampResult:
    """Inherit parent-generation status into child DB at seed time.

    Alias for :func:`stamp_parent_metadata` satisfying the AC:
    ``Function defined: bob.parent_gen.inherit_parent_status``.

    When ``spawn_next_generation.sh`` seeds bob_(N+1), call this function to
    propagate completed/needs_human/regression status from bob_N's DB.

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob.db``.

    Returns:
        :class:`StampResult` with counts of rows stamped / skipped.

    Raises:
        FileNotFoundError: If either DB path does not exist.
        ValueError: If ``parent_db_path`` is ``None`` or otherwise invalid.
    """
    return stamp_parent_metadata(
        parent_db_path=parent_db_path,
        child_db_path=child_db_path,
    )


def _load_parent_by_slot(parent_db_path: pathlib.Path) -> dict[str, dict]:
    """Return qualifying parent feature rows indexed by spec_slot."""
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
    return {row["spec_slot"]: dict(row) for row in rows}


def _load_child_features(child_db_path: pathlib.Path) -> list[dict]:
    """Return all feature rows from the child DB."""
    conn = sqlite3.connect(str(child_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, spec_slot FROM features").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _fetch_evidence_hash(db_path: pathlib.Path, feature_id: str) -> str | None:
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
