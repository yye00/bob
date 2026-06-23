"""Deterministic pytest snapshots — disable xdist early-halt.

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

enforce_maxfail_for_xdist(argv) -> list[str]
    Enforce --maxfail=0 specifically at the xdist boundary. When xdist
    flags (-n / --numprocesses / --dist) are absent the argv is returned
    unchanged. When xdist flags are present, --maxfail=0 is injected and
    any existing --maxfail is stripped.
"""

from __future__ import annotations

import re

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
_XDIST_FLAGS = frozenset(["-n", "--numprocesses", "--dist"])
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


def enforce_maxfail_for_xdist(argv: list[str]) -> list[str]:
    """Enforce --maxfail=0 only when xdist parallelism flags are present.

    When pytest-xdist is active (-n / --numprocesses / --dist), individual
    worker processes may halt after hitting the default maxfail threshold,
    producing non-deterministic before/after snapshots. This function
    detects xdist flags and injects --maxfail=0 to ensure the full test
    matrix is always collected.

    When no xdist flags are present the argv is returned unchanged; a
    serial pytest run already collects all results without early-halt.

    Args:
        argv: Base pytest argument list. May contain xdist flags and/or a
            --maxfail value.

    Returns:
        When xdist flags detected: new list with exactly one --maxfail=0
        positioned immediately after the first element (the pytest command).
        When no xdist flags detected: argv unchanged (same object).
    """
    has_xdist = any(arg in _XDIST_FLAGS or arg.startswith("--numprocesses=") for arg in argv)
    if not has_xdist:
        return argv
    return enforce_maxfail_zero(argv)
