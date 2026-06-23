"""Migration: add parent_status, parent_completed_at, parent_evidence_hash to features.

These three columns carry reproducibility provenance from the parent generation's
DB into the child generation at seed time (feature e1b5bacb — F-R7-420 prereq).

* parent_status         – the feature's status value in the parent DB
                          (e.g. 'completed', 'needs_human', 'regression')
* parent_completed_at   – ISO-8601 timestamp of when the parent row was last
                          updated (proxy for completion time)
* parent_evidence_hash  – SHA-256 of the most-recent evidence artifact content
                          from the parent DB, used by the disk reconciler and
                          sticky-completed gate for provenance checks
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def upgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add parent provenance columns to features table. Idempotent."""
    resolved_db = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(resolved_db))
    try:
        _add_column_if_missing(conn, "features", "parent_status", "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "features", "parent_completed_at", "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "features", "parent_evidence_hash", "TEXT DEFAULT NULL")
        conn.commit()
    finally:
        conn.close()


def _resolve_db_path(db_path: Union[str, pathlib.Path, None]) -> pathlib.Path:
    if db_path is not None:
        return pathlib.Path(db_path)
    import os
    env_path = os.environ.get("BOB3_DATABASE_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path("bob3.db")


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, col_def: str
) -> None:
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
