"""Schema management helpers for bob databases.

Provides functions to evolve the database schema without requiring
a full ORM migration framework.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def backfill_spec_slots(
    db_path: Union[str, pathlib.Path],
    spec_path: Union[str, pathlib.Path],
) -> int:
    """Backfill spec_slot for existing rows by parsing the spec YAML and matching by name.

    Ensures the spec_slot column exists (calls add_spec_slot_column) and then
    populates NULL spec_slot values by matching feature names to spec YAML keys.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    spec_path:
        Path to the spec YAML file whose keys provide the spec_slot values.

    Returns
    -------
    int
        Number of feature rows updated with a spec_slot value.

    Raises
    ------
    ValueError
        If db_path or spec_path is None, empty, or not a str/Path.
    FileNotFoundError
        If spec_path does not exist.
    """
    if db_path is None:
        raise ValueError("db_path must not be None")
    if isinstance(db_path, str) and not db_path.strip():
        raise ValueError("db_path must not be an empty string")
    if not isinstance(db_path, (str, pathlib.Path)):
        raise ValueError(f"db_path must be a str or Path, got {type(db_path).__name__}")
    if spec_path is None:
        raise ValueError("spec_path must not be None")
    if isinstance(spec_path, str) and not str(spec_path).strip():
        raise ValueError("spec_path must not be an empty string")
    if not isinstance(spec_path, (str, pathlib.Path)):
        raise ValueError(f"spec_path must be a str or Path, got {type(spec_path).__name__}")

    add_spec_slot_column(db_path)

    import yaml

    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    raw_features = spec.get("features") if isinstance(spec, dict) else None
    if not isinstance(raw_features, dict):
        return 0

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

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, name FROM features WHERE spec_slot IS NULL"
        ).fetchall()

        updated = 0
        for fid, fname in rows:
            slot = name_to_slot.get(fname)
            if slot is not None:
                conn.execute(
                    "UPDATE features SET spec_slot = ? WHERE id = ?",
                    (slot, fid),
                )
                updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def add_spec_slot_column(
    db_path: Union[str, pathlib.Path],
) -> bool:
    """Add the spec_slot column to the features table if it is absent.

    The spec_slot column stores a stable cross-generation identifier derived
    from the YAML spec key (e.g. "F-R6-200"). Without it, the convergence
    detector falls back to comparing by UUID, which is minted fresh on every
    ``bob init`` and always produces a 100% divergence result.

    This function is idempotent: calling it when the column already exists
    is a no-op.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.

    Returns
    -------
    bool
        ``True`` if the column was added, ``False`` if it already existed.

    Raises
    ------
    ValueError
        If db_path is None, empty, or not a str/Path.
    sqlite3.DatabaseError
        If the database file is corrupt or cannot be opened.
    """
    if db_path is None:
        raise ValueError("db_path must not be None")
    if isinstance(db_path, str) and not db_path.strip():
        raise ValueError("db_path must not be an empty string")
    if not isinstance(db_path, (str, pathlib.Path)):
        raise ValueError(f"db_path must be a str or Path, got {type(db_path).__name__}")

    conn = sqlite3.connect(str(db_path))
    try:
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(features)").fetchall()
        }
        if "spec_slot" in existing:
            return False
        conn.execute("ALTER TABLE features ADD COLUMN spec_slot TEXT DEFAULT NULL")
        conn.commit()
        return True
    finally:
        conn.close()
