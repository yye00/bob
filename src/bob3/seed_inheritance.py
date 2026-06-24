"""Seed-time parent-generation DB inheritance for bob3 (F-R7-400).

Entry point for ``spawn_next_generation.sh``: when seeding bob_(N+1), call
:func:`apply_parent_generation_data` to stamp every matched child feature row
with provenance from the parent DB.

Delegates to :mod:`bob3.parent_gen_db_inheritance` for the low-level read/stamp
operations so the canonical logic lives in one place.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import NamedTuple

from bob3.parent_gen_db_inheritance import read_parent_features, stamp_child_row

logger = logging.getLogger(__name__)


class SeedInheritanceResult(NamedTuple):
    """Summary returned by :func:`apply_parent_generation_data`."""

    stamped: int
    skipped_no_slot: int
    skipped_no_parent_match: int


def stamp_parent_generation(
    *,
    parent_db_path: "str | os.PathLike[str]",
    child_db_path: "str | os.PathLike[str] | None" = None,
) -> SeedInheritanceResult:
    """Alias for :func:`apply_parent_generation_data` satisfying the F-R7-400 AC name contract.

    When spawn_next_generation.sh seeds bob_(N+1), call this function to read every
    completed/needs_human/regression feature row from bob_N's bob3.db, match by
    spec_slot, and stamp the matched bob_(N+1) row with parent_status,
    parent_completed_at, parent_evidence_hash.

    Args:
        parent_db_path: Path to bob_N's ``bob3.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob3.db``. Defaults to
                        ``BOB3_DATABASE_PATH`` env var or ``bob3.db`` in cwd.

    Returns:
        :class:`SeedInheritanceResult` with stamped/skipped counts.

    Raises:
        FileNotFoundError: If parent_db_path or child_db_path does not exist.
        ValueError: If parent_db_path is None or empty.
    """
    return apply_parent_generation_data(
        parent_db_path=parent_db_path,
        child_db_path=child_db_path,
    )


def apply_parent_generation_data(
    *,
    parent_db_path: "str | os.PathLike[str]",
    child_db_path: "str | os.PathLike[str] | None" = None,
) -> SeedInheritanceResult:
    """Stamp child-generation feature rows with provenance from the parent DB.

    Reads every completed/needs_human/regression feature row from bob_N's DB,
    matches by ``spec_slot`` against bob_(N+1)'s features, and writes
    ``parent_status``, ``parent_completed_at``, and ``parent_evidence_hash``
    into each matched child row.

    Args:
        parent_db_path: Path to bob_N's ``bob3.db``.
        child_db_path:  Path to bob_(N+1)'s ``bob3.db``.  Defaults to the
                        ``BOB3_DATABASE_PATH`` env var or ``bob3.db`` in cwd.

    Returns:
        :class:`SeedInheritanceResult` with stamped/skipped counts.

    Raises:
        FileNotFoundError: If parent_db_path or child_db_path does not exist.
        ValueError: If parent_db_path is None or empty.
    """
    if parent_db_path is None:
        raise ValueError("parent_db_path must not be None")
    if str(parent_db_path) == "":
        raise ValueError("parent_db_path must not be an empty string")

    parent_db_path = pathlib.Path(parent_db_path)

    if child_db_path is None:
        env_path = os.environ.get("BOB3_DATABASE_PATH")
        child_db_path = pathlib.Path(env_path) if env_path else pathlib.Path("bob3.db")
    else:
        child_db_path = pathlib.Path(child_db_path)

    if not parent_db_path.exists():
        raise FileNotFoundError(f"Parent DB not found: {parent_db_path}")
    if not child_db_path.exists():
        raise FileNotFoundError(f"Child DB not found: {child_db_path}")

    import sqlite3

    parent_rows = read_parent_features(parent_db_path)

    conn = sqlite3.connect(str(child_db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        child_rows = conn.execute(
            "SELECT id, spec_slot FROM features"
        ).fetchall()
    finally:
        conn.close()

    stamped = 0
    skipped_no_slot = 0
    skipped_no_parent_match = 0

    for row in child_rows:
        slot = row["spec_slot"]
        if not slot:
            skipped_no_slot += 1
            continue
        parent = parent_rows.get(slot)
        if parent is None:
            skipped_no_parent_match += 1
            continue
        stamp_child_row(
            child_db_path=child_db_path,
            feature_id=row["id"],
            parent_status=parent.status,
            parent_completed_at=parent.updated_at,
            parent_evidence_hash=parent.evidence_hash,
        )
        stamped += 1
        logger.info(
            "seed_inheritance: stamped child feature slot=%s parent_status=%s",
            slot,
            parent.status,
        )

    logger.info(
        "seed_inheritance: done stamped=%d skipped_no_slot=%d skipped_no_parent_match=%d",
        stamped,
        skipped_no_slot,
        skipped_no_parent_match,
    )
    return SeedInheritanceResult(
        stamped=stamped,
        skipped_no_slot=skipped_no_slot,
        skipped_no_parent_match=skipped_no_parent_match,
    )
