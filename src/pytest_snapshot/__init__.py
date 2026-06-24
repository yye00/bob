"""pytest_snapshot — deterministic pytest snapshot helpers.

Enforces --maxfail=0 at the snapshot boundary to prevent non-deterministic
early-halt when pytest-xdist is active.

Public API
----------
snapshot(argv) -> list[str]
    Enforce --maxfail=0 at the snapshot boundary. Alias for
    maxfail_enforcer.enforce_maxfail_zero.
"""

from __future__ import annotations

from pytest_snapshot.maxfail_enforcer import enforce_maxfail_zero, MAXFAIL_ZERO

# Primary entry point for snapshot callers
snapshot = enforce_maxfail_zero

__all__ = ["snapshot", "enforce_maxfail_zero", "MAXFAIL_ZERO"]
