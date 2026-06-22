"""Python companion to tools/weekend_watchdog.sh.

Provides programmatic access to convergence detection logic so other
Python modules (tests, CLI, orchestrator) can call check_convergence
without shelling out to bash.
"""

from __future__ import annotations

import pathlib
from typing import Union

from bob3.migrations.add_spec_slot import get_completed_spec_slots
from bob3.orchestrator.convergence import compares_by_spec_slot


def check_convergence(
    db_a: Union[str, pathlib.Path],
    db_b: Union[str, pathlib.Path],
) -> tuple[bool, set[str]]:
    """Compare two bob3 databases by completed spec_slot sets.

    Returns (converged, symmetric_difference).  converged is True when the
    symmetric difference is empty (same feature set across generations).

    Uses get_completed_spec_slots so that comparison is stable across
    ``bob3 init`` runs that mint fresh UUIDs.

    Args:
        db_a: Path to first SQLite database.
        db_b: Path to second SQLite database.

    Returns:
        Tuple of (converged: bool, diff: set[str]) where diff is the
        symmetric difference of completed spec_slots.
    """
    compares_by_spec_slot()  # raises ValueError if spec_slot column absent
    slots_a = get_completed_spec_slots(db_a)
    slots_b = get_completed_spec_slots(db_b)
    diff = slots_a.symmetric_difference(slots_b)
    return (len(diff) == 0, diff)


def convergence_report(
    db_a: Union[str, pathlib.Path],
    db_b: Union[str, pathlib.Path],
) -> str:
    """Return a human-readable convergence report string.

    Args:
        db_a: Path to first SQLite database.
        db_b: Path to second SQLite database.

    Returns:
        Report string, suitable for logging.
    """
    converged, diff = check_convergence(db_a, db_b)
    slots_a = get_completed_spec_slots(db_a)
    if converged:
        return f"CONVERGED — both dbs share {len(slots_a)} completed spec_slot(s)"
    return (
        f"DIVERGED — {len(diff)} spec_slot(s) differ: {sorted(diff)}"
    )
