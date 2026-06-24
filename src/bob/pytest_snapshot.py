"""bob.pytest_snapshot — deterministic pytest snapshot enforcement.

pytest with xdist halts after approximately 20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. The snapshot
path MUST run pytest with --maxfail=0; if xdist is used, --maxfail=0
MUST be enforced at the snapshot boundary.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected immediately after the first
    element and any existing --maxfail flag stripped, guaranteeing a
    deterministic snapshot regardless of xdist worker count.
"""

from __future__ import annotations

import re

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
MAXFAIL_ZERO = "--maxfail=0"

__all__ = ["enforce_maxfail_zero", "MAXFAIL_ZERO"]


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Return argv with --maxfail=0 injected at the snapshot boundary.

    Strips any existing --maxfail flag (including non-zero values and
    duplicate --maxfail=0 entries) and injects --maxfail=0 immediately
    after the first element (the pytest command), ensuring it appears
    before any xdist -n / --numprocesses flags.

    Args:
        argv: Base pytest argument list. Must be a list of strings. May
              contain any --maxfail value; it will be replaced with
              --maxfail=0.

    Returns:
        New list with exactly one --maxfail=0, positioned at index 1
        (or index 0 when argv is empty).

    Raises:
        ValueError: If argv is not a list, or contains non-string elements.
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
