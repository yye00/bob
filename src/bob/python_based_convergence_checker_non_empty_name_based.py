"""Python-based convergence checker with non-empty + name-based comparison.

Root cause of 2026-05-23 weekend_watchdog silent exits:
  1. Shell-out to `sqlite3` CLI (not installed) returned empty strings silently.
  2. Empty results triggered false-positive convergence.
  3. Secondary bug compared UUID `id` instead of feature `name`.

This module fixes both bugs: uses stdlib sqlite3 (no shell-out) and compares
by feature name. It also guards against empty completed sets to prevent
false-positive convergence when a generation has no finished features.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union


def _completed_names(db_path: Union[str, Path]) -> set[str]:
    """Return completed feature names from db_path using stdlib sqlite3."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM features WHERE status = 'completed'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def python_based_convergence_checker_non_empty_name_based(
    db0: Union[str, Path],
    db1: Union[str, Path],
    db2: Union[str, Path],
) -> tuple[bool, set[str]]:
    """Check convergence across three generation databases using stdlib sqlite3.

    Fixes two root causes of false-positive convergence:
      1. Non-empty guard: returns (False, set()) if any generation has zero
         completed features, preventing empty-result false positives from a
         missing sqlite3 CLI.
      2. Name-based comparison: compares feature.name (not feature.id/UUID),
         so fresh ``bob init`` runs that mint new UUIDs do not break detection.

    Parameters
    ----------
    db0, db1, db2:
        Paths to three consecutive generation SQLite databases.

    Returns
    -------
    tuple[bool, set[str]]
        ``(converged, diff)`` where converged is True only when all three
        non-empty name sets are identical, and diff is the symmetric difference
        of the union of all three sets minus the intersection (empty on convergence).
    """
    for db in (db0, db1, db2):
        if not Path(db).exists():
            return (False, set())

    c0 = _completed_names(db0)
    c1 = _completed_names(db1)
    c2 = _completed_names(db2)

    # Non-empty guard: an empty set means no completed features → false positive risk
    if not c0 or not c1 or not c2:
        return (False, set())

    if c0 == c1 == c2:
        return (True, set())

    all_names = c0 | c1 | c2
    common = c0 & c1 & c2
    diff = all_names - common
    return (False, diff)
