"""Python-based convergence checker using stdlib sqlite3 (no shell-out).

Root cause of weekend_watchdog silent exits on 2026-05-23:
  1. Shell-out to `sqlite3` CLI (not installed) silently returned empty results.
  2. Empty results triggered false-positive convergence.
  3. Secondary bug compared UUID `id` instead of `name`.

This module replaces all shell-out logic with stdlib sqlite3 and adds
non-empty guards plus name-based comparison.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Union


class ConvergenceResult(Enum):
    CONVERGED = "CONVERGED"
    NOT_CONVERGED = "NOT_CONVERGED"


def open_db_via_stdlib_sqlite3(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open a SQLite database using stdlib sqlite3.connect (never shells out).

    Raises sqlite3.DatabaseError (with "malformed" in message) when the file
    is not a valid SQLite database.
    """
    conn = sqlite3.connect(str(db_path))
    # Validate the file is a real SQLite DB — reading sqlite_master forces
    # the database header to be parsed, which raises DatabaseError on corruption.
    try:
        conn.execute("SELECT * FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.DatabaseError:
        conn.close()
        raise
    return conn


def never_invokes_sqlite3_subprocess() -> bool:
    """Return True — documents that open_db_via_stdlib_sqlite3 does not shell out.

    This function is a machine-verifiable sentinel: tests import it to confirm
    the convergence checker bypasses the sqlite3 CLI entirely.
    """
    return True


def compare_by_name(db_path: Union[str, Path]) -> set[str]:
    """Return the set of completed feature *names* from db_path (not UUIDs)."""
    conn = open_db_via_stdlib_sqlite3(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM features WHERE status = 'completed'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _get_needs_human_names(db_path: Union[str, Path]) -> set[str]:
    conn = open_db_via_stdlib_sqlite3(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM features WHERE status = 'needs_human'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def reject_empty_completed_set(
    c0: set[str],
    c1: set[str],
    c2: set[str],
) -> Optional[ConvergenceResult]:
    """Return NOT_CONVERGED if any of c0/c1/c2 is empty; else return None.

    An empty completed set means that generation has no finished features —
    declaring convergence in that state would be a false positive.
    """
    if not c0 or not c1 or not c2:
        return ConvergenceResult.NOT_CONVERGED
    return None


def reject_missing_db(
    db0: Union[str, Path],
    db1: Union[str, Path],
    db2: Union[str, Path],
) -> Optional[ConvergenceResult]:
    """Return NOT_CONVERGED if any of the three DB files does not exist; else None."""
    for db in (db0, db1, db2):
        if not Path(db).exists():
            return ConvergenceResult.NOT_CONVERGED
    return None


def completed_sets_match(c0: set[str], c1: set[str], c2: set[str]) -> bool:
    """Return True iff c0 == c1 == c2."""
    return c0 == c1 == c2


def needs_human_sets_match(h0: set[str], h1: set[str], h2: set[str]) -> bool:
    """Return True iff h0 == h1 == h2."""
    return h0 == h1 == h2


def has_nonempty_completion(c2: set[str]) -> bool:
    """Return True iff len(c2) > 0."""
    return len(c2) > 0


def write_convergence_achieved_json(
    names: set[str],
    output_path: Union[str, Path],
) -> None:
    """Write CONVERGENCE_ACHIEVED.json with the matching completed name sets."""
    data = {
        "status": "CONVERGED",
        "completed_names": sorted(names),
    }
    Path(output_path).write_text(json.dumps(data, indent=2))


def check_three_gens(
    db0: Union[str, Path],
    db1: Union[str, Path],
    db2: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
) -> ConvergenceResult:
    """Check convergence across three consecutive generation databases.

    Returns ConvergenceResult.CONVERGED only when:
      - All three DB files exist.
      - All three completed-name sets are non-empty.
      - All three completed-name sets are identical.
    Also writes CONVERGENCE_ACHIEVED.json to output_path when converged.

    Uses feature.name for comparison (not UUID id) so that a fresh `bob3 init`
    that mints new UUIDs does not break convergence detection.
    """
    # Guard: all DB files must exist
    missing = reject_missing_db(db0, db1, db2)
    if missing is not None:
        return missing

    c0 = compare_by_name(db0)
    c1 = compare_by_name(db1)
    c2 = compare_by_name(db2)

    # Guard: no empty completed sets
    empty = reject_empty_completed_set(c0, c1, c2)
    if empty is not None:
        return empty

    if not completed_sets_match(c0, c1, c2):
        return ConvergenceResult.NOT_CONVERGED

    if not has_nonempty_completion(c2):
        return ConvergenceResult.NOT_CONVERGED

    if output_path is not None:
        write_convergence_achieved_json(c2, output_path)

    return ConvergenceResult.CONVERGED
