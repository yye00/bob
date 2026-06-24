"""Parent-gen DB inheritance at seed time (06e6bcbe — F-R7-400).

Entry point called by ``spawn_next_generation.sh`` when seeding bob_(N+1).
Reads every completed/needs_human/regression feature row from bob_N's
bob.db, matches by spec_slot against the child DB's features, and stamps
parent_status, parent_completed_at, and parent_evidence_hash onto each
matched child row.
"""

from __future__ import annotations

from bob.orchestrator.parent_gen_inheritance import (
    InheritanceResult,
    inherit_from_parent_db,
)

import pathlib


def parent_gen_db_inheritance_seed_time(
    *,
    parent_db_path: str | pathlib.Path,
    child_db_path: str | pathlib.Path | None = None,
) -> InheritanceResult:
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
        InheritanceResult(stamped, skipped_no_slot, skipped_no_parent_match).

    Raises:
        FileNotFoundError: If either DB path does not exist.
    """
    return inherit_from_parent_db(
        parent_db_path=parent_db_path,
        child_db_path=child_db_path,
    )
