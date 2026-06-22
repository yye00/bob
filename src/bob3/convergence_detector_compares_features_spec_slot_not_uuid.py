"""Convergence detector that compares features by spec_slot, not UUID.

The weekend_watchdog.sh:check_convergence function historically compared
feature sets by features.id (UUID), which is minted fresh on every ``bob3 init``,
causing the cross-generation diff to always be 100%.

This module provides ``convergence_detector_compares_features_spec_slot_not_uuid``
which performs the correct comparison using the stable ``spec_slot`` column
(derived from the YAML spec key, e.g. "F-R6-200") so that convergence detection
is meaningful across generations.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Union

from bob3.migrations.add_spec_slot import get_completed_spec_slots


def convergence_detector_compares_features_spec_slot_not_uuid(
    db_a: Union[str, pathlib.Path],
    db_b: Union[str, pathlib.Path],
) -> tuple[bool, set[str]]:
    """Compare two bob3 databases by completed spec_slot sets, not by UUID.

    Feature IDs (UUID) are minted fresh on every ``bob3 init``, making UUID-based
    cross-generation set diffs always 100% divergent.  This function instead
    compares the stable ``spec_slot`` column values so that convergence detection
    reflects whether the same *features* (by spec key) were completed.

    Features with ``spec_slot = NULL`` are excluded from comparison.
    Only features with ``status = 'completed'`` are included.

    Parameters
    ----------
    db_a:
        Path to the first generation's SQLite database.
    db_b:
        Path to the second generation's SQLite database.

    Returns
    -------
    tuple[bool, set[str]]
        A pair ``(converged, diff)`` where:
        - ``converged`` is ``True`` when the symmetric difference of spec_slot
          sets is empty (same feature set across generations).
        - ``diff`` is the symmetric difference set (empty when converged).

    Raises
    ------
    sqlite3.DatabaseError
        If either database file is corrupt or cannot be opened.
    """
    slots_a = get_completed_spec_slots(db_a)
    slots_b = get_completed_spec_slots(db_b)
    diff = slots_a.symmetric_difference(slots_b)
    return (len(diff) == 0, diff)


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

    # Record how many rows have NULL spec_slot before the migration
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
