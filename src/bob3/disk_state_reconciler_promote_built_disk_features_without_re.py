"""Disk-state reconciler — promote built-on-disk features without re-spawn.

Every generation re-runs every ready feature even when its acceptance-criteria
artifacts already exist on disk from the parent generation.  This module
provides ``disk_state_reconciler_promote_built_disk_features_without_re``
which evaluates each AC entry against the workspace and atomically promotes
features whose artifacts pass, avoiding redundant sub-agent spawns.
"""

from __future__ import annotations

import pathlib

from bob3.orchestrator.disk_reconciler import reconcile_from_disk


def disk_state_reconciler_promote_built_disk_features_without_re(
    project_id: str,
    workspace: pathlib.Path | None = None,
) -> int:
    """Promote features whose on-disk state satisfies all verifiable ACs.

    Evaluates each AC entry for every ``'ready'`` or ``'pending'`` feature
    against the workspace filesystem.  Features whose every AC passes are
    atomically transitioned to ``'completed'`` with a ``disk_reconciliation``
    evidence artifact, preventing redundant re-execution by the sub-agent
    spawner.

    Parameters
    ----------
    project_id:
        UUID of the project whose features are to be reconciled.
    workspace:
        Root path of the project workspace.  Defaults to ``pathlib.Path.cwd()``.

    Returns
    -------
    int
        Number of features promoted to ``'completed'`` in this call.

    Raises
    ------
    ValueError
        If ``project_id`` is empty.
    """
    if not project_id:
        raise ValueError(
            "project_id must be a non-empty string, got: {!r}".format(project_id)
        )

    return reconcile_from_disk(project_id=project_id, workspace=workspace)


__all__ = ["disk_state_reconciler_promote_built_disk_features_without_re"]
