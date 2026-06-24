"""Observer module for characterization AC — exposes observe_target_behavior.

This module is the public entry point for the observer phase of the
characterization AC kind. It wraps :func:`bob.acceptance.kinds.observe_and_snapshot`
with a simplified signature for use by bob's AC verifier and orchestrator
when they need to pin down current behavior before editing brownfield code.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    observe_and_snapshot,
    parse_characterization_ac,
)


def observe_target_behavior(
    ac_spec: dict[str, Any] | str | CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> SnapshotResult:
    """Observer phase: capture current behavior as approval-file snapshots.

    Resolves the characterization AC from *ac_spec*, invokes the target
    callable with each sample input, and writes captured outputs (stdout,
    return value) to snapshot files in ``ac.snapshot_dir``.

    This must be called **before** any implementation changes so the snapshot
    files represent the ground-truth baseline.

    Args:
        ac_spec:   A :class:`CharacterizationAC` instance, a dict with a
                   ``'characterization'`` key, or an inline ``'characterization:'``
                   string.
        workspace: Workspace root used to resolve file paths. Defaults to the
                   current working directory.

    Returns:
        A :class:`SnapshotResult` with ``success``, ``snapshot_files``, and
        ``errors`` fields.

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


def run_characterization_observer(
    ac: CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> SnapshotResult:
    """Observer phase: run target with sample_inputs and write snapshot files.

    Thin wrapper around :func:`observe_and_snapshot` that accepts a resolved
    :class:`CharacterizationAC` directly.

    Args:
        ac:        A parsed :class:`CharacterizationAC` to observe.
        workspace: Workspace root. Defaults to the current working directory.

    Returns:
        A :class:`SnapshotResult` with ``success``, ``snapshot_files``,
        and ``errors`` fields.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()
    return observe_and_snapshot(ac, ws)


__all__ = ["observe_target_behavior", "run_characterization_observer"]
