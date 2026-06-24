"""Migration: add model_tier column to features table (F-R7-633).

model_tier is the feature's current position in the model-escalation ladder
(BOB3_MODEL_ESCALATION_LADDER). Default 0 = the first (least capable) ladder
entry. When a feature exhausts its attempts at tier N and a stronger model
exists at tier N+1, the orchestrator bumps model_tier and resets attempts
instead of marking the feature needs_human. See bob3.model_escalation.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def upgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add model_tier column to features table.

    Safe to run multiple times (idempotent).
    """
    resolved_db = _resolve_db_path(db_path)

    conn = sqlite3.connect(str(resolved_db))
    try:
        _add_column_if_missing(
            conn, "features", "model_tier", "INTEGER DEFAULT 0"
        )
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
