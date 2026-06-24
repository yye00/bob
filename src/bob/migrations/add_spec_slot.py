"""Migration: add spec_slot column to features table.

spec_slot is a stable cross-generation identifier derived from the YAML spec key
(e.g. "F-R6-200"). It lets the convergence detector compare feature sets across
generations without being confused by freshly-minted UUIDs.

Usage:
    from bob.migrations.add_spec_slot import upgrade
    upgrade(db_path="/path/to/bob.db")                          # column only
    upgrade(db_path="/path/to/bob.db", spec_path="spec.yaml")   # + backfill
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def upgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
    spec_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add spec_slot column to features table and optionally backfill from spec YAML.

    Safe to run multiple times (idempotent).

    Args:
        db_path: Path to the SQLite database. Defaults to the BOB_DATABASE_PATH
                 env var or ./bob.db.
        spec_path: Optional path to a spec YAML file. When provided, existing rows
                   whose spec_slot is NULL are backfilled by matching feature name
                   against the spec keys' title/name fields.
    """
    resolved_db = _resolve_db_path(db_path)

    conn = sqlite3.connect(str(resolved_db))
    try:
        _add_column_if_missing(conn, "features", "spec_slot", "TEXT DEFAULT NULL")
        conn.commit()

        if spec_path is not None:
            _backfill_from_spec(conn, pathlib.Path(spec_path))
            conn.commit()
    finally:
        conn.close()


def downgrade(
    *,
    db_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Remove spec_slot column from features table.

    SQLite does not support DROP COLUMN before version 3.35.0.  On older
    SQLite builds this is a no-op (logged to stderr) so the migration remains
    safe to call unconditionally.

    Args:
        db_path: Path to the SQLite database.
    """
    import sys
    import sqlite3 as _sqlite3

    resolved_db = _resolve_db_path(db_path)
    conn = _sqlite3.connect(str(resolved_db))
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        if "spec_slot" not in existing:
            return  # already absent — nothing to do

        # DROP COLUMN requires SQLite >= 3.35.0
        sqlite_version = tuple(int(x) for x in _sqlite3.sqlite_version.split("."))
        if sqlite_version < (3, 35, 0):
            print(
                f"[add_spec_slot.downgrade] SQLite {_sqlite3.sqlite_version} < 3.35.0 "
                "— DROP COLUMN not supported; spec_slot column left in place.",
                file=sys.stderr,
            )
            return

        conn.execute("ALTER TABLE features DROP COLUMN spec_slot")
        conn.commit()
    finally:
        conn.close()


def get_completed_spec_slots(
    db_path: Union[str, pathlib.Path],
) -> set:
    """Return the set of spec_slot values for all completed features in db_path.

    Features with spec_slot=NULL are excluded. Only features with status='completed'
    are included.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        A set of spec_slot strings.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # Gracefully handle databases that predate the migration (no spec_slot column).
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        if "spec_slot" not in cols:
            return set()

        rows = conn.execute(
            "SELECT spec_slot FROM features WHERE status = 'completed' AND spec_slot IS NOT NULL"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_db_path(db_path: Union[str, pathlib.Path, None]) -> pathlib.Path:
    if db_path is not None:
        return pathlib.Path(db_path)
    import os
    env_path = os.environ.get("BOB_DATABASE_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path("bob.db")


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def _backfill_from_spec(conn: sqlite3.Connection, spec_path: pathlib.Path) -> None:
    """Populate spec_slot for existing rows by matching feature names to spec keys."""
    import yaml

    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    raw_features = spec.get("features") if isinstance(spec, dict) else None
    if not isinstance(raw_features, dict):
        return

    # Build a map from feature name → spec key
    name_to_slot: dict[str, str] = {}
    for slot_key, feat_val in raw_features.items():
        if isinstance(feat_val, dict):
            name = feat_val.get("title") or feat_val.get("name")
        elif isinstance(feat_val, str):
            name = feat_val
        else:
            name = None
        if name:
            name_to_slot[str(name)] = str(slot_key)

    # Fetch features that have no spec_slot yet
    rows = conn.execute(
        "SELECT id, name FROM features WHERE spec_slot IS NULL"
    ).fetchall()

    for fid, fname in rows:
        slot = name_to_slot.get(fname)
        if slot is not None:
            conn.execute(
                "UPDATE features SET spec_slot = ? WHERE id = ?",
                (slot, fid),
            )
