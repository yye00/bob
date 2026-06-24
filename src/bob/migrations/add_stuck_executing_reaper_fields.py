"""Migration: add subagent_pid and subagent_heartbeat_at columns to features table.

These fields support the stuck-executing reaper (b596a38a): the reaper checks
whether the subagent process is still alive and whether the heartbeat is recent
enough, then resets 'executing' features to 'ready' when the subagent has died.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def upgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add subagent_pid and subagent_heartbeat_at columns to features table.

    Safe to run multiple times (idempotent).
    """
    resolved_db = _resolve_db_path(db_path)

    conn = sqlite3.connect(str(resolved_db))
    try:
        _add_column_if_missing(conn, "features", "subagent_pid", "INTEGER DEFAULT NULL")
        _add_column_if_missing(
            conn, "features", "subagent_heartbeat_at", "TIMESTAMP DEFAULT NULL"
        )
        conn.commit()
    finally:
        conn.close()


def _resolve_db_path(db_path: Union[str, pathlib.Path, None]) -> pathlib.Path:
    if db_path is not None:
        return pathlib.Path(db_path)
    import os
    env_path = os.environ.get("BOB_DATABASE_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path("bob.db")


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, col_def: str
) -> None:
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
