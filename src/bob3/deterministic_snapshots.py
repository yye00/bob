"""bob3.deterministic_snapshots — enforce --maxfail=0 at snapshot boundaries.

pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. Snapshot
path MUST run pytest with --maxfail=0; if xdist is used,
--maxfail=0 MUST be enforced at the snapshot boundary.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected and any existing --maxfail flag
    stripped, guaranteeing deterministic before/after snapshots regardless
    of xdist worker count.

snapshot_with_maxfail(argv, *, run_fn=None) -> list[str]
    High-level wrapper: enforce --maxfail=0 and return the patched argv
    (or pass it to run_fn if provided).

MAXFAIL_ZERO : str
    The canonical flag value injected at snapshot boundaries (``"--maxfail=0"``).
"""

from __future__ import annotations

import re
from typing import Callable

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
MAXFAIL_ZERO = "--maxfail=0"

__all__ = ["enforce_maxfail_zero", "snapshot_with_maxfail", "MAXFAIL_ZERO"]


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Return argv with --maxfail=0 injected at the pytest snapshot boundary.

    Strips any existing --maxfail flag (including non-zero values and
    duplicate --maxfail=0 entries) and injects --maxfail=0 immediately
    after the first element (the pytest command), ensuring it appears
    before any xdist -n / --numprocesses flags.

    This prevents pytest-xdist from halting early (~20-25 failures) so
    that before/after snapshots always cover the same set of test node IDs,
    making regression comparison reliable.

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


def snapshot_with_maxfail(
    argv: list[str],
    *,
    run_fn: Callable[[list[str]], object] | None = None,
) -> list[str]:
    """Enforce --maxfail=0 and optionally execute the patched argv.

    High-level snapshot boundary helper. Always calls enforce_maxfail_zero
    to ensure the full test suite runs. If run_fn is provided, it is called
    with the patched argv (e.g. subprocess.check_call). The patched argv is
    always returned so callers can inspect or log it.

    Args:
        argv:   Base pytest argument list passed to enforce_maxfail_zero.
        run_fn: Optional callable invoked with the patched argv. If None,
                the patched argv is returned without executing anything.

    Returns:
        Patched argv list with exactly one --maxfail=0.

    Raises:
        ValueError: If argv is not a list of strings (propagated from
                    enforce_maxfail_zero).
    """
    patched = enforce_maxfail_zero(argv)
    if run_fn is not None:
        run_fn(patched)
    return patched
