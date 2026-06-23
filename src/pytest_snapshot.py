"""Deterministic pytest snapshot helper — enforce --maxfail=0 at snapshot boundary.

pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. The snapshot
path MUST run pytest with --maxfail=0; if xdist is used, --maxfail=0
MUST be enforced at the snapshot boundary.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected and any existing --maxfail
    flag stripped, guaranteeing a deterministic snapshot regardless of
    xdist worker count.

enforce_maxfail_with_xdist(argv) -> list[str]
    Alias for enforce_maxfail_zero, kept for backward compatibility.
"""

from __future__ import annotations

import re

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
MAXFAIL_ZERO = "--maxfail=0"


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Return argv with --maxfail=0 injected at the snapshot boundary.

    Strips any existing --maxfail flag (including non-zero values and
    duplicate --maxfail=0 entries) and injects --maxfail=0 immediately
    after the first element (the pytest command), ensuring it appears
    before any xdist -n / --numprocesses flags.

    Args:
        argv: Base pytest argument list. May contain any --maxfail value.

    Returns:
        New list with exactly one --maxfail=0, positioned at index 1
        (or index 0 when argv is empty).
    """
    cleaned = [arg for arg in argv if not _MAXFAIL_RE.match(arg)]
    if cleaned:
        return [cleaned[0], MAXFAIL_ZERO] + cleaned[1:]
    return [MAXFAIL_ZERO]


enforce_maxfail_with_xdist = enforce_maxfail_zero
