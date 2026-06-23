"""bob3.snapshot_enforcer — enforce --maxfail=0 at the pytest snapshot boundary.

pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets.  The snapshot
path MUST run pytest with --maxfail=0; if xdist is used, --maxfail=0
MUST be enforced at the snapshot boundary.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected immediately after the first
    element and any existing --maxfail flag stripped, guaranteeing a
    deterministic snapshot regardless of xdist worker count.

Integrates with pytest_plugins.snapshot_maxfail_enforcer — delegates to
the same logic to ensure consistent behaviour at the snapshot boundary.
"""

from __future__ import annotations

from pytest_plugins import snapshot_maxfail_enforcer

__all__ = ["enforce_maxfail_zero"]


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Return argv with --maxfail=0 enforced at the snapshot boundary.

    Strips any existing --maxfail flag (including non-zero values and
    duplicate --maxfail=0 entries) and injects --maxfail=0 immediately
    after the first element (the pytest command), ensuring it appears
    before any xdist -n / --numprocesses flags.

    Delegates to pytest_plugins.snapshot_maxfail_enforcer to remain
    consistent with the plugin-level enforcement.

    Args:
        argv: Base pytest argument list.  Must be a list of strings.
              Passing ``None`` or a non-list raises ``ValueError``.
              Individual non-string elements also raise ``ValueError``.

    Returns:
        New list with exactly one ``--maxfail=0``, positioned at index 1
        (or index 0 when *argv* is empty).

    Raises:
        ValueError: If *argv* is not a list of strings.
    """
    return snapshot_maxfail_enforcer(argv)
