"""bob3.deterministic_snapshot — enforce --maxfail=0 at the pytest snapshot boundary.

pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. Snapshot
path MUST run pytest with --maxfail=0; if xdist is used,
--maxfail=0 MUST be enforced at the snapshot boundary.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected and any existing --maxfail
    flag stripped, guaranteeing a deterministic snapshot regardless of
    xdist worker count.

MAXFAIL_ZERO : str
    The canonical flag value injected at snapshot boundaries (``"--maxfail=0"``).
"""

from __future__ import annotations

from bob3.pytest_snapshots import (  # noqa: F401
    MAXFAIL_ZERO,
    enforce_maxfail_zero,
)

__all__ = ["enforce_maxfail_zero", "MAXFAIL_ZERO"]
