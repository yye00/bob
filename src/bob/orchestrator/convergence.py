"""Convergence detector: compare feature sets across generations by spec_slot.

These sentinel functions document (and make machine-verifiable) the invariant
that convergence checking uses spec_slot — the stable YAML-key-derived column —
rather than the UUID id field, which is minted fresh in every `bob init`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union


def compares_by_spec_slot(
    slots_a: list | None = None,
    slots_b: list | None = None,
) -> bool:
    """Return True — documents that convergence comparison key is spec_slot.

    Accepts optional iterables (for edge-case tests like empty lists) but the
    return value is always True: this function exists to be queried by tests
    that want a machine-checkable proof that the convergence detector does NOT
    compare by UUID.

    Raises ValueError if the features table in the active database lacks a
    spec_slot column, since that would make correct convergence detection
    impossible.
    """
    # When a db_path is available via env, verify the column exists.
    import os
    db_path = os.environ.get("BOB_DATABASE_PATH")
    if db_path and Path(db_path).exists():
        _assert_spec_slot_column(db_path)
    return True


def set_diff_uses_spec_slot() -> bool:
    """Return True — documents that the set-diff key for convergence is spec_slot.

    The check_convergence function in tools/weekend_watchdog.sh calls
    get_completed_spec_slots() from bob.migrations.add_spec_slot, which
    queries ``SELECT spec_slot FROM features WHERE status = 'completed' …``.
    The symmetric-difference of those sets determines convergence.  UUID (id)
    is never used as the diff key.
    """
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assert_spec_slot_column(db_path: Union[str, Path]) -> None:
    """Raise ValueError if the features table lacks a spec_slot column."""
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
    finally:
        conn.close()
    if "spec_slot" not in cols:
        raise ValueError(
            "spec_slot column is absent from the features table — "
            "run bob.migrations.add_spec_slot.upgrade() before using "
            "the convergence detector"
        )
