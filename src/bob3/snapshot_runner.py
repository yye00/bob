"""snapshot_runner — enforce --maxfail=0 at the pytest snapshot boundary.

pytest-xdist halts after approximately 20–25 failures non-deterministically.
When the verifier's before/after snapshots run with xdist active, different
subsets of tests are executed in each snapshot, making regression comparison
unreliable.

This module provides ``enforce_maxfail_zero``, which strips any existing
``--maxfail`` flag and injects ``--maxfail=0`` immediately after the first
element (the pytest command), so that it appears before any xdist ``-n``
flags and cannot be overridden.

Public API
----------
enforce_maxfail_zero(argv: list[str]) -> list[str]
    Return a new argv with exactly one ``--maxfail=0``, placed at index 1
    (or index 0 when argv is empty).

MAXFAIL_ZERO : str
    The canonical flag injected at the snapshot boundary (``"--maxfail=0"``).
"""

from __future__ import annotations

import re

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
MAXFAIL_ZERO = "--maxfail=0"

__all__ = ["MAXFAIL_ZERO", "enforce_maxfail_zero"]


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Enforce ``--maxfail=0`` at the pytest snapshot boundary.

    Strips any existing ``--maxfail`` flag and injects ``--maxfail=0``
    immediately after the first element (the pytest command), so that it
    appears before any xdist ``-n`` / ``--numprocesses`` flags.

    This ensures that the full test set always runs regardless of how many
    tests are failing, making before/after snapshots cover the same set of
    test node IDs and therefore comparable.

    Args:
        argv: Base pytest argument list. May contain any ``--maxfail`` value.
              Must be a list of strings; passing ``None`` or a non-list raises
              ``ValueError``.

    Returns:
        New list with exactly one ``--maxfail=0``, positioned at index 1
        (or index 0 when *argv* is empty).

    Raises:
        ValueError: If *argv* is not a list of strings.
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
