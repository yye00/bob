"""Convergence detector — compares features by spec_slot, not UUID.

The weekend_watchdog.sh:check_convergence function historically compared
feature sets by features.id (UUID), which is minted fresh on every
``bob3 init``, causing the cross-generation diff to always be 100%.

This module provides ``check_convergence`` which performs the correct
comparison using the stable ``spec_slot`` column (derived from the YAML
spec key, e.g. "F-R6-200") so that convergence detection is meaningful
across generations.  It also backfills spec_slot for existing rows.

Integration: bob3.weekend_watchdog re-exports check_convergence from here.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union

from bob3.convergence import check_convergence  # noqa: F401 — primary export
from bob3.convergence import check_convergence_by_spec_slot  # noqa: F401


def backfill_spec_slot(
    db_path: Union[str, pathlib.Path],
    spec_path: Union[str, pathlib.Path],
) -> int:
    """Backfill spec_slot for existing rows by parsing the spec YAML and matching by name.

    Runs the add_spec_slot migration (idempotent) and returns the number of
    rows that were updated.

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
            before = conn.execute(
                "SELECT COUNT(*) FROM features WHERE spec_slot IS NULL"
            ).fetchone()[0]
        else:
            before = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    finally:
        conn.close()

    upgrade(db_path=db_path, spec_path=spec_path)

    conn = sqlite3.connect(str(db_path))
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM features WHERE spec_slot IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()

    return max(0, before - after)


__all__ = [
    "check_convergence",
    "check_convergence_by_spec_slot",
    "backfill_spec_slot",
]
