"""Migration: add permanent_forward_carry column to features table.

This column supports the spec_quality_gate allowlist (b61bdeb5):
when True, a feature bypasses the 0.85 spec_quality_score gate
regardless of its actual score.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
from typing import Union


def upgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add permanent_forward_carry column to features table.

    Safe to run multiple times (idempotent).
    """
    resolved_db = _resolve_db_path(db_path)

    conn = sqlite3.connect(str(resolved_db))
    try:
        _add_column_if_missing(
            conn, "features", "permanent_forward_carry", "BOOLEAN DEFAULT FALSE"
        )
        conn.commit()
    finally:
        conn.close()


def _resolve_db_path(db_path: Union[str, pathlib.Path, None]) -> pathlib.Path:
    if db_path is not None:
        return pathlib.Path(db_path)
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
