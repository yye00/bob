"""maxfail_enforcer — enforce --maxfail=0 at the pytest snapshot boundary.

pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. This module
enforces --maxfail=0 at the snapshot boundary to guarantee deterministic
snapshots regardless of xdist worker count.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected and any existing --maxfail
    flag stripped.
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
              Must be a list of strings. Passing None or a non-list raises
              ValueError. List elements must all be strings.

    Returns:
        New list with exactly one --maxfail=0, positioned at index 1
        (or index 0 when argv is empty).

    Raises:
        ValueError: If argv is not a list of strings.
    """
    if not isinstance(argv, list):
        raise ValueError(
            f"argv must be a list of strings, got {type(argv).__name__!r}"
        )
    for i, arg in enumerate(argv):
        if not isinstance(arg, str):
            raise ValueError(
                f"argv[{i}] must be a str, got {type(arg).__name__!r}: {arg!r}"
            )

    cleaned = [arg for arg in argv if not _MAXFAIL_RE.match(arg)]
    if cleaned:
        return [cleaned[0], MAXFAIL_ZERO] + cleaned[1:]
    return [MAXFAIL_ZERO]
