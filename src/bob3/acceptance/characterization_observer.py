"""Characterization observer module for BF-6 — re-export shim.

Exposes :func:`observe_and_snapshot` at the
``bob3.acceptance.characterization_observer`` import path, satisfying the
acceptance criterion:
  "Function defined: bob3.acceptance.characterization_observer.observe_and_snapshot"

All implementation lives in :mod:`bob3.acceptance.kinds`.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob3.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


def observe_target_behavior(
    ac_spec: dict[str, Any] | str | CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> SnapshotResult:
    """Observer phase: capture current behavior as approval-file snapshots.

    Resolves the characterization AC from *ac_spec*, invokes the target
    callable with each sample input, and writes captured outputs to snapshot
    files in ``ac.snapshot_dir``.

    Args:
        ac_spec:   A :class:`CharacterizationAC`, a dict with a
                   ``'characterization'`` key, or an inline
                   ``'characterization:'`` string.
        workspace: Workspace root used to resolve file paths. Defaults to
                   the current working directory.

    Returns:
        A :class:`SnapshotResult` with ``success``, ``snapshot_files``,
        and ``errors`` fields.

    Raises:
        ValueError: If *ac_spec* cannot be parsed as a characterization AC.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()

    if isinstance(ac_spec, CharacterizationAC):
        ac = ac_spec
    else:
        ac = parse_characterization_ac(ac_spec)
        if ac is None:
            raise ValueError(
                f"Cannot parse characterization AC from: {ac_spec!r}"
            )

    return observe_and_snapshot(ac, ws)


__all__ = [
    "CharacterizationAC",
    "SnapshotResult",
    "VerificationResult",
    "observe_and_snapshot",
    "observe_target_behavior",
    "parse_characterization_ac",
    "verify_against_snapshots",
]
