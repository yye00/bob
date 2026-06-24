"""Parent-gen DB inheritance at seed time — public entry point (F-R7-400).

Called by ``spawn_next_generation.sh`` when seeding bob_(N+1).  Reads every
completed/needs_human/regression feature row from bob_N's bob.db, matches
by spec_slot against the child DB's features, and stamps parent_status,
parent_completed_at, and parent_evidence_hash onto each matched child row.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import NamedTuple

from bob.orchestrator.parent_gen_inheritance import (
    InheritanceResult,
    inherit_from_parent_db,
)

logger = logging.getLogger(__name__)


class InheritParentStatusResult(NamedTuple):
    """Summary returned by :func:`inherit_parent_status`."""

    stamped: int
    skipped_no_slot: int
    skipped_no_parent_match: int


def inherit_parent_status(
    *,
    parent_db_path: "str | os.PathLike[str]",
    child_db_path: "str | os.PathLike[str] | None" = None,
) -> InheritParentStatusResult:
    """Stamp child-generation features with provenance from the parent DB at seed time.

    When spawn_next_generation.sh seeds bob_(N+1), call this function to
    propagate completed/needs_human/regression status across generation
    boundaries.  For every child feature whose spec_slot matches a qualifying
    parent row, writes parent_status, parent_completed_at, and
    parent_evidence_hash.

    Args:
        parent_db_path: Path to bob_N's bob.db.
        child_db_path:  Path to bob_(N+1)'s bob.db.  Defaults to the
                        BOB_DATABASE_PATH env var or bob.db in cwd.

    Returns:
        :class:`InheritParentStatusResult` with stamped/skipped counts.

    Raises:
        FileNotFoundError: If parent_db_path or child_db_path does not exist.
        ValueError: If parent_db_path is None or empty.
    """
    if parent_db_path is None:
        raise ValueError("parent_db_path must not be None")
    if str(parent_db_path) == "":
        raise ValueError("parent_db_path must not be an empty string")

    result: InheritanceResult = inherit_from_parent_db(
        parent_db_path=pathlib.Path(parent_db_path),
        child_db_path=pathlib.Path(child_db_path) if child_db_path is not None else None,
    )

    logger.info(
        "inherit_parent_status: stamped=%d skipped_no_slot=%d skipped_no_parent_match=%d",
        result.stamped,
        result.skipped_no_slot,
        result.skipped_no_parent_match,
    )

    return InheritParentStatusResult(
        stamped=result.stamped,
        skipped_no_slot=result.skipped_no_slot,
        skipped_no_parent_match=result.skipped_no_parent_match,
    )
