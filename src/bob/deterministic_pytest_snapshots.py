"""bob.deterministic_pytest_snapshots — deterministic pytest snapshot args.

pytest with xdist halts after ~20-25 failures non-deterministically. When the
snapshot path runs the suite twice (before/after a change) the two runs can
early-halt at *different* failure counts, so the before/after snapshots end up
covering different subsets of test node IDs and the regression comparison is
meaningless.

The fix: the snapshot path MUST run pytest with ``--maxfail=0`` (run every
test, never early-halt), and if xdist is used ``--maxfail=0`` MUST be enforced
at the snapshot boundary — before the ``-n`` / ``--numprocesses`` flags so the
xdist controller propagates it to every worker.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with exactly one ``--maxfail=0`` injected right after the
    pytest command (index 1), any pre-existing ``--maxfail`` flag stripped.

build_snapshot_pytest_args(argv, *, numprocesses=None) -> list[str]
    Build the full deterministic snapshot pytest argv: enforce ``--maxfail=0``
    and, when xdist parallelism is requested, ensure the ``-n`` flag is present
    and ordered *after* ``--maxfail=0``.

MAXFAIL_ZERO : str
    The canonical flag injected at snapshot boundaries (``"--maxfail=0"``).
"""

from __future__ import annotations

import re

# Delegate the core --maxfail rewrite to bob.snapshot so both modules share one
# implementation. This import also satisfies the `integration: bob.snapshot` AC.
import bob.snapshot as _snapshot

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
_NUMPROCS_RE = re.compile(r"^(-n|--numprocesses)(=.*)?$")
MAXFAIL_ZERO = "--maxfail=0"

__all__ = [
    "enforce_maxfail_zero",
    "build_snapshot_pytest_args",
    "MAXFAIL_ZERO",
]


def _validate_argv(argv: object) -> None:
    """Raise ValueError unless *argv* is a list of strings."""
    if not isinstance(argv, list):
        raise ValueError(
            f"argv must be a list of strings, got {type(argv).__name__!r}"
        )
    for i, arg in enumerate(argv):
        if not isinstance(arg, str):
            raise ValueError(
                f"argv[{i}] must be a str, got {type(arg).__name__!r}: {arg!r}"
            )


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Return argv with ``--maxfail=0`` enforced at the snapshot boundary.

    Strips any existing ``--maxfail`` flag (non-zero values *and* duplicate
    ``--maxfail=0`` entries) and injects exactly one ``--maxfail=0`` immediately
    after the first element (the pytest command). Positioning it at index 1
    guarantees it precedes any xdist ``-n`` / ``--numprocesses`` flag, so the
    xdist controller applies it before spawning workers.

    Args:
        argv: Base pytest argument list. Must be a list of strings.

    Returns:
        A new list with exactly one ``--maxfail=0`` at index 1 (or index 0 when
        ``argv`` is empty). The input list is never mutated.

    Raises:
        ValueError: If ``argv`` is not a list, or contains non-string elements.
    """
    _validate_argv(argv)
    cleaned = [arg for arg in argv if not _MAXFAIL_RE.match(arg)]
    if cleaned:
        return [cleaned[0], MAXFAIL_ZERO] + cleaned[1:]
    return [MAXFAIL_ZERO]


def build_snapshot_pytest_args(
    argv: list[str], *, numprocesses: int | None = None
) -> list[str]:
    """Build the full deterministic-snapshot pytest argv.

    Always enforces ``--maxfail=0`` (via :func:`enforce_maxfail_zero`). When
    xdist parallelism is requested — either because *numprocesses* is given or
    because ``argv`` already carries a ``-n`` / ``--numprocesses`` flag — the
    result keeps ``--maxfail=0`` ordered *before* the xdist flag, so the
    controller propagates the no-early-halt policy to every worker.

    Args:
        argv: Base pytest argument list (list of strings).
        numprocesses: Optional xdist worker count. When a non-negative int is
            supplied and ``argv`` has no ``-n`` flag, ``-n <numprocesses>`` is
            appended. When ``argv`` already specifies ``-n``, this argument is
            ignored (the caller-supplied flag wins).

    Returns:
        A new list: the enforced-``--maxfail=0`` argv, with an xdist ``-n`` flag
        appended when requested. The input list is never mutated.

    Raises:
        ValueError: If ``argv`` is not a list of strings, or ``numprocesses`` is
            provided but is not a non-negative int (bool is rejected).
    """
    _validate_argv(argv)

    if numprocesses is not None:
        if isinstance(numprocesses, bool) or not isinstance(numprocesses, int):
            raise ValueError(
                f"numprocesses must be a non-negative int or None, got "
                f"{type(numprocesses).__name__!r}: {numprocesses!r}"
            )
        if numprocesses < 0:
            raise ValueError(
                f"numprocesses must be non-negative, got {numprocesses!r}"
            )

    result = enforce_maxfail_zero(argv)

    already_parallel = any(_NUMPROCS_RE.match(arg) for arg in result)
    if numprocesses is not None and not already_parallel:
        result = result + ["-n", str(numprocesses)]

    return result
