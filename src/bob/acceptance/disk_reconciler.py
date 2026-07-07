"""Disk-reconciler extension for the characterization AC kind (BF-6).

The base disk reconciler (:mod:`bob.orchestrator.disk_reconciler`) promotes a
feature to ``completed`` when its acceptance-criteria artifacts already exist on
disk. Characterization ACs (:mod:`bob.acceptance.kinds`) produce a distinct kind
of artifact — the baseline snapshot files written by the observer phase into
``ac.snapshot_dir``. This module lets the reconciler treat those snapshot files
as AC-satisfaction artifacts so a characterized feature is not needlessly re-run.

Public API
----------
snapshot_artifacts(ac, workspace) -> list[pathlib.Path]
    Return the snapshot ``.txt`` files that currently satisfy *ac*.

characterization_artifacts_present(ac, workspace) -> bool
    True when *ac* has at least one snapshot artifact on disk.

reconcile_characterization_ac(ac, workspace) -> tuple[bool, str]
    Evaluate a characterization AC against on-disk state: the AC is satisfied
    when snapshots exist AND the current behavior still matches them.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob.acceptance.kinds import (
    CharacterizationAC,
    parse_characterization_ac,
    verify_against_snapshots,
)


def _coerce_ac(ac: Any) -> CharacterizationAC | None:
    """Return a :class:`CharacterizationAC` from *ac* (already-parsed or raw)."""
    if isinstance(ac, CharacterizationAC):
        return ac
    return parse_characterization_ac(ac)


def snapshot_artifacts(ac: Any, workspace: pathlib.Path | str) -> list[pathlib.Path]:
    """Return the snapshot ``.txt`` files that satisfy characterization *ac*.

    Args:
        ac:        A parsed :class:`CharacterizationAC` or a raw AC dict/string.
        workspace: Project workspace root.

    Returns:
        Sorted list of snapshot file paths under ``ac.snapshot_dir``. Empty if
        *ac* is not a characterization AC or no snapshots have been captured.
    """
    parsed = _coerce_ac(ac)
    if parsed is None:
        return []
    snap_dir = pathlib.Path(workspace) / parsed.snapshot_dir
    if not snap_dir.exists():
        return []
    return sorted(snap_dir.glob("*.txt"))


def characterization_artifacts_present(ac: Any, workspace: pathlib.Path | str) -> bool:
    """Return True when characterization *ac* has snapshot artifacts on disk."""
    return len(snapshot_artifacts(ac, workspace)) > 0


def reconcile_characterization_ac(
    ac: Any, workspace: pathlib.Path | str
) -> tuple[bool, str]:
    """Evaluate a characterization AC against on-disk state for reconciliation.

    The AC is considered satisfied only when both hold:

    1. Snapshot artifacts exist in ``ac.snapshot_dir`` (observer phase ran).
    2. Re-running the target still matches those snapshots (no regression).

    Args:
        ac:        A parsed :class:`CharacterizationAC` or a raw AC dict/string.
        workspace: Project workspace root.

    Returns:
        ``(passed, detail)`` where *detail* is a human-readable summary suitable
        for evidence recording.
    """
    parsed = _coerce_ac(ac)
    if parsed is None:
        return False, "Not a characterization AC — cannot reconcile from disk."

    ws = pathlib.Path(workspace)
    artifacts = snapshot_artifacts(parsed, ws)
    if not artifacts:
        return (
            False,
            f"No snapshot artifacts in {parsed.snapshot_dir}; observer phase not run.",
        )

    result = verify_against_snapshots(parsed, ws)
    detail = (
        f"{len(artifacts)} snapshot artifact(s) present; {result.details}"
    )
    return result.passed, detail


__all__ = [
    "snapshot_artifacts",
    "characterization_artifacts_present",
    "reconcile_characterization_ac",
]
