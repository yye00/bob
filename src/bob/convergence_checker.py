"""Python-based convergence checker with non-empty + name-based comparison.

Fixes the 2026-05-23 weekend_watchdog silent exits caused by:
  1. Shell-out to sqlite3 CLI (not installed) returning empty strings silently.
  2. Empty results triggering false-positive convergence.
  3. Secondary bug comparing UUID id instead of feature name.

Uses stdlib sqlite3 (no shell-out) and compares by name, not UUID.
Guards against empty completed sets to prevent false-positive convergence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union


def _validate_db_path(path: Union[str, Path], name: str) -> None:
    if path is None:
        raise ValueError(f"{name} must not be None")
    if isinstance(path, str) and not path.strip():
        raise ValueError(f"{name} must not be an empty string")
    if not isinstance(path, (str, Path)):
        raise ValueError(f"{name} must be a str or Path, got {type(path).__name__}")


def query_features(db_path: Union[str, Path]) -> set[str]:
    """Return the set of completed feature NAMES from a generation database.

    Uses stdlib sqlite3 (never shells out to the sqlite3 CLI). Compares by
    ``name`` — the stable spec identity — not by ``id`` (a UUID minted fresh
    on every ``bob init``). A missing database file returns an empty set so
    callers can treat "not yet created" as "no completed features" rather
    than crashing.

    Parameters
    ----------
    db_path:
        Path to a generation SQLite database.

    Returns
    -------
    set[str]
        Names of features whose status is ``completed`` (empty if none, or
        if the database file does not exist).

    Raises
    ------
    ValueError
        If ``db_path`` is None, an empty string, or not a str/Path.
    """
    _validate_db_path(db_path, "db_path")

    if not Path(db_path).exists():
        return set()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM features WHERE status = 'completed'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _completed_names(db_path: Union[str, Path]) -> set[str]:
    """Return completed feature names using stdlib sqlite3."""
    return query_features(db_path)


def check_convergence(
    db0: Union[str, Path],
    db1: Union[str, Path],
    db2: Union[str, Path],
) -> tuple[bool, set[str]]:
    """Check convergence across three generation databases using stdlib sqlite3.

    Fixes two root causes of false-positive convergence:
      1. Non-empty guard: returns (False, set()) if any generation has zero
         completed features, preventing false positives from empty results.
      2. Name-based comparison: compares feature.name (not UUID id), so fresh
         bob init runs that mint new UUIDs do not break detection.

    Parameters
    ----------
    db0, db1, db2:
        Paths to three consecutive generation SQLite databases.

    Returns
    -------
    tuple[bool, set[str]]
        (converged, diff) where converged is True only when all three non-empty
        name sets are identical.

    Raises
    ------
    ValueError
        If any path is None, empty string, or not a str/Path.
    """
    _validate_db_path(db0, "db0")
    _validate_db_path(db1, "db1")
    _validate_db_path(db2, "db2")

    # Missing db file → not converged (guards against missing sqlite3 CLI scenario)
    for db in (db0, db1, db2):
        if not Path(db).exists():
            return (False, set())

    c0 = _completed_names(db0)
    c1 = _completed_names(db1)
    c2 = _completed_names(db2)

    # Non-empty guard: empty set means no completed features → false positive risk
    if not c0 or not c1 or not c2:
        return (False, set())

    if c0 == c1 == c2:
        return (True, set())

    all_names = c0 | c1 | c2
    common = c0 & c1 & c2
    diff = all_names - common
    return (False, diff)


def compare_by_name(
    set_a: set[str],
    set_b: set[str],
) -> tuple[bool, set[str]]:
    """Compare two completed-feature name sets.

    Returns (True, set()) when both non-empty sets are identical.
    Returns (False, diff) if they differ, or (False, set()) if either is empty.
    Both arguments must be sets; passing any other type raises ValueError.

    Raises
    ------
    ValueError
        If either argument is not a set.
    """
    if not isinstance(set_a, set):
        raise ValueError(f"set_a must be a set, got {type(set_a).__name__}")
    if not isinstance(set_b, set):
        raise ValueError(f"set_b must be a set, got {type(set_b).__name__}")

    if not set_a or not set_b:
        return (False, set())

    diff = set_a.symmetric_difference(set_b)
    return (len(diff) == 0, diff)
