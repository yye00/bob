"""DB inheritance module for bob — public API for parent-gen provenance at seed time.

Exposes :func:`inherit_parent_metadata` as the canonical entry point called by
``spawn_next_generation.sh`` when seeding bob_(N+1) from bob_N.

This module is a thin re-export of the implementation in
:mod:`bob.parent_gen_db_inheritance` so the acceptance criteria
``bob.db_inheritance.inherit_parent_metadata`` resolves correctly.
"""

from __future__ import annotations

from bob.parent_gen_db_inheritance import (  # noqa: F401
    ParentFeatureRow,
    StampResult,
    inherit_parent_metadata,
    inherit_parent_status,
    read_parent_features,
    stamp_child_row,
    stamp_parent_metadata,
)

__all__ = [
    "inherit_parent_metadata",
    "inherit_parent_status",
    "read_parent_features",
    "stamp_child_row",
    "stamp_parent_metadata",
    "ParentFeatureRow",
    "StampResult",
]
