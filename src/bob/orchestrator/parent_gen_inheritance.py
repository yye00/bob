"""Parent-generation DB inheritance at seed time (e1b5bacb — F-R7-420 prereq).

When ``spawn_next_generation.sh`` seeds bob_(N+1), call
:func:`inherit_from_parent_db` to copy provenance from bob_N's DB into the
new generation's features.  For every feature in the child DB that has a
``spec_slot`` value, we look for a matching row in the parent DB with
``status`` in ``{'completed', 'needs_human', 'regression'}``.  If found, we
stamp the child row with:

* ``parent_status``        — the status value from the parent row
* ``parent_completed_at``  — ``updated_at`` from the parent row (proxy for
                             completion timestamp)
* ``parent_evidence_hash`` — SHA-256 of the most-recent ``is_current=1``
                             evidence artifact for that feature in the parent DB

These stamps give the sticky-completed gate (eb3c74d9) and the disk reconciler
(2f69b554) reliable provenance to act on across generation boundaries.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sqlite3
from datetime import datetime
from typing import NamedTuple

logger = logging.getLogger(__name__)

_PARENT_STATUSES = frozenset({"completed", "needs_human", "regression"})


class InheritanceResult(NamedTuple):
    """Summary returned by :func:`inherit_from_parent_db`."""

    stamped: int
    skipped_no_slot: int
    skipped_no_parent_match: int


def inherit_from_parent_db(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path | None = None,
) -> InheritanceResult:
    """Stamp child-generation features with provenance from the parent DB.

    Reads every completed/needs_human/regression feature row from the parent
    DB, matches by ``spec_slot`` against the child DB's features, and writes
    ``parent_status``, ``parent_completed_at``, ``parent_evidence_hash`` into
    the matched child rows.

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob.db``.  Defaults to the
                        value of the ``BOB_DATABASE_PATH`` env var or
                        ``bob.db`` in the current working directory.

    Returns:
        :class:`InheritanceResult` with counts of rows stamped / skipped.
    """
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

    parent_rows = _load_parent_rows(parent_db_path)
    parent_by_slot: dict[str, dict] = {
        r["spec_slot"]: r for r in parent_rows if r["spec_slot"]
    }

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

            evidence_hash = _fetch_latest_evidence_hash(parent_db_path, parent["id"])
            parent_completed_at = parent.get("updated_at")

            child_conn.execute(
                """UPDATE features
                   SET parent_status = ?,
                       parent_completed_at = ?,
                       parent_evidence_hash = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (
                    parent["status"],
                    parent_completed_at,
                    evidence_hash,
                    datetime.now().isoformat(),
                    child["id"],
                ),
            )
            logger.info(
                "Stamped feature %s (slot=%s) with parent_status=%s",
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
        "inherit_from_parent_db: stamped=%d skipped_no_slot=%d skipped_no_parent_match=%d",
        stamped,
        skipped_no_slot,
        skipped_no_parent_match,
    )
    return InheritanceResult(
        stamped=stamped,
        skipped_no_slot=skipped_no_slot,
        skipped_no_parent_match=skipped_no_parent_match,
    )


def match_by_spec_slot(parent_db_path: str | pathlib.Path) -> dict[str, dict]:
    """Return a dict mapping spec_slot to the parent feature row.

    Only rows whose ``status`` is in ``{'completed', 'needs_human', 'regression'}``
    are included.  If the parent DB does not exist, returns an empty dict (see
    :func:`handle_missing_parent_db`).

    Args:
        parent_db_path: Path to bob_N's ``bob.db``.

    Returns:
        ``{spec_slot: feature_row_dict}`` for every qualifying parent row.
    """
    parent_db_path = pathlib.Path(parent_db_path)
    if not parent_db_path.exists():
        return handle_missing_parent_db(parent_db_path)
    rows = _load_parent_rows(parent_db_path)
    return {r["spec_slot"]: r for r in rows if r.get("spec_slot")}


def stamp_provenance(
    *,
    child_db_path: str | pathlib.Path,
    feature_id: str,
    parent_status: str,
    parent_completed_at: str | None,
    parent_evidence_hash: str | None,
) -> None:
    """Atomically write parent provenance fields onto a child feature row.

    Writes ``parent_status``, ``parent_completed_at``, and
    ``parent_evidence_hash`` in a single UPDATE inside a transaction.

    Args:
        child_db_path:        Path to bob_(N+1)'s ``bob.db``.
        feature_id:           UUID of the child feature row to stamp.
        parent_status:        Status copied from the parent feature row.
        parent_completed_at:  Timestamp copied from the parent feature row.
        parent_evidence_hash: SHA-256 of the parent's evidence artifact.
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


def handle_missing_parent_db(parent_db_path: str | pathlib.Path) -> dict:
    """Return an empty dict when the parent DB is absent; never raises FileNotFoundError.

    Called when the parent-generation DB path does not exist (e.g. first
    generation has no predecessor).  Logging at DEBUG level lets operators
    distinguish intentional first-gen seeding from accidental path errors.

    Args:
        parent_db_path: The path that was expected but not found.

    Returns:
        Empty dict — callers treat this as "no parent matches available".
    """
    logger.debug("Parent DB not found (first-gen seed?): %s", parent_db_path)
    return {}


def _load_parent_rows(parent_db_path: pathlib.Path) -> list[dict]:
    """Return completed/needs_human/regression feature rows from the parent DB."""
    conn = sqlite3.connect(str(parent_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in _PARENT_STATUSES)
        rows = conn.execute(
            f"SELECT id, spec_slot, status, updated_at FROM features "
            f"WHERE status IN ({placeholders}) AND spec_slot IS NOT NULL",
            list(_PARENT_STATUSES),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _load_child_features(child_db_path: pathlib.Path) -> list[dict]:
    """Return all feature rows from the child DB."""
    conn = sqlite3.connect(str(child_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, spec_slot FROM features").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _fetch_latest_evidence_hash(
    parent_db_path: pathlib.Path,
    feature_id: str,
) -> str | None:
    """Return SHA-256 of the most-recent current evidence artifact, or None."""
    conn = sqlite3.connect(str(parent_db_path), timeout=30)
    try:
        row = conn.execute(
            """SELECT content FROM evidence_artifacts
               WHERE feature_id = ? AND is_current = 1
               ORDER BY created_at DESC LIMIT 1""",
            (feature_id,),
        ).fetchone()
        if row is None:
            return None
        content = row[0] or ""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    finally:
        conn.close()
