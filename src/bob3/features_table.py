"""Features table utilities — spec_slot column management.

Provides add_spec_slot_column, the primary entrypoint for adding and backfilling
the stable spec_slot column to the features table.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union


def add_spec_slot_column(
    db_path: Union[str, pathlib.Path, None] = None,
    spec_path: Union[str, pathlib.Path, None] = None,
) -> None:
    """Add spec_slot column to the features table and optionally backfill from spec YAML.

    The spec_slot column holds a stable cross-generation identifier derived from
    the YAML spec key (e.g. "F-R6-200"). It lets the convergence detector compare
    feature sets across generations without being confused by freshly-minted UUIDs.

    Safe to run multiple times (idempotent).

    Parameters
    ----------
    db_path:
        Path to the SQLite database. Defaults to the ``BOB3_DATABASE_PATH`` env var
        or ``./bob3.db``.
    spec_path:
        Optional path to a spec YAML file. When provided, existing rows whose
        spec_slot is NULL are backfilled by matching feature name against spec
        keys' title/name fields.
    """
    from bob3.migrations.add_spec_slot import upgrade

    upgrade(db_path=db_path, spec_path=spec_path)


def backfill_spec_slot(
    db_path: Union[str, pathlib.Path],
    spec_path: Union[str, pathlib.Path],
) -> int:
    """Backfill spec_slot for existing rows by parsing the spec YAML and matching by name.

    Runs the add_spec_slot migration (idempotent) then counts how many rows
    gained a spec_slot value.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.
    spec_path:
        Path to the spec YAML file whose keys provide the spec_slot values.

    Returns
    -------
    int
        Number of feature rows updated with a spec_slot value.
    """
    from bob3.migrations.add_spec_slot import upgrade

    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        if "spec_slot" in cols:
            before_null = conn.execute(
                "SELECT COUNT(*) FROM features WHERE spec_slot IS NULL"
            ).fetchone()[0]
        else:
            before_null = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    finally:
        conn.close()

    upgrade(db_path=db_path, spec_path=spec_path)

    conn = sqlite3.connect(str(db_path))
    try:
        after_null = conn.execute(
            "SELECT COUNT(*) FROM features WHERE spec_slot IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()

    return max(0, before_null - after_null)
