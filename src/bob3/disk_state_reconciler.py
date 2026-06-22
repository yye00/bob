"""Disk-state reconciler for Bob3 (feature a7d1be1c).

Every generation re-runs every ready feature even when its acceptance-criteria
artifacts already exist on disk from the parent generation. This module
provides :func:`reconcile_from_disk` which evaluates each AC entry against
the workspace and atomically promotes features whose artifacts pass in isolation,
avoiding redundant sub-agent spawns.

Integration: called from ``bob3.orchestrator`` to promote features before
spawning new sub-agents.
"""

from __future__ import annotations

import pathlib

from bob3.orchestrator.disk_reconciler import reconcile_from_disk as _reconcile_from_disk


def reconcile_from_disk(project_id: str, workspace: pathlib.Path | None = None) -> int:
    """Promote features whose on-disk state satisfies all verifiable ACs.

    Evaluates each AC entry for every ``'ready'`` or ``'pending'`` feature
    against the workspace filesystem. Features whose every AC passes are
    atomically transitioned to ``'completed'`` with a ``disk_reconciliation``
    evidence artifact, preventing redundant re-execution by the sub-agent
    spawner.

    Parameters
    ----------
    project_id:
        UUID of the project whose features are to be reconciled. Must be
        a non-empty string; raises ``ValueError`` otherwise.
    workspace:
        Root path of the project workspace. Defaults to
        ``pathlib.Path.cwd()``.

    Returns
    -------
    int
        Number of features promoted to ``'completed'`` in this call.

    Raises
    ------
    ValueError
        If ``project_id`` is empty, ``None``, or whitespace-only.
    """
    if not project_id or (isinstance(project_id, str) and not project_id.strip()):
        raise ValueError(
            "project_id must be a non-empty string, got: {!r}".format(project_id)
        )

    return _reconcile_from_disk(project_id=project_id, workspace=workspace)


__all__ = ["reconcile_from_disk"]
