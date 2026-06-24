"""Migration: add test_files column to features and unattributed_failures table.

test_files: JSON array of test_*.py files owned by a feature.
  Required for regression attribution — a feature may only be demoted to
  'regression' if its OWN test files newly fail.

unattributed_failures: stores newly-failing tests that cannot be mapped to
  any feature owner.  They are recorded here instead of being scapegoated
  onto an arbitrary completed feature.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def upgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add test_files column and unattributed_failures table.

    Safe to run multiple times (idempotent).
    """
    resolved_db = _resolve_db_path(db_path)

    conn = sqlite3.connect(str(resolved_db))
    try:
        _add_column_if_missing(
            conn, "features", "test_files", "TEXT DEFAULT NULL"
        )
        _create_unattributed_failures_if_missing(conn)
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


def _create_unattributed_failures_if_missing(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "unattributed_failures" not in tables:
        conn.execute(
            """CREATE TABLE unattributed_failures (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                causing_feature_id TEXT NOT NULL REFERENCES features(id),
                test_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            """CREATE INDEX idx_unattributed_failures_project
               ON unattributed_failures(project_id)"""
        )
        conn.execute(
            """CREATE INDEX idx_unattributed_failures_causing
               ON unattributed_failures(causing_feature_id)"""
        )
