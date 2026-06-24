"""Sticky-completed gate — re-evaluation cannot un-complete persisted work.

If a feature was status='completed' in the parent generation's DB AND its
acceptance criteria still verify on disk, no evaluator FAIL or
regression-cascade vote may flip its status below 'ready'. The stamp is
reset only when a refinement attempt actually rewrites one of the AC-named
source files.
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob.models import Feature

from bob.orchestrator.sticky_completed import may_demote


def sticky_completed_gate_re_evaluation_cannot_un_complete(
    feature: "Feature",
    *,
    target_status: str,
    workspace: pathlib.Path | None = None,
) -> bool:
    """Return True if it is safe to demote *feature* to *target_status*.

    This gate enforces that once a feature was completed in the parent
    generation (``parent_completed=True``) and its acceptance-criteria
    artifacts still verify on disk, no evaluator FAIL or regression-cascade
    vote may flip its status below 'ready'.

    The stamp is reset only when a refinement attempt actually rewrites one
    of the AC-named source files (via ``clear_on_real_edit``).

    Args:
        feature: The Feature model instance being evaluated.
        target_status: The status the caller wants to assign.
        workspace: Workspace root for disk-based AC evaluation.
            Defaults to ``pathlib.Path.cwd()``.

    Returns:
        ``True`` if demotion may proceed, ``False`` if the sticky gate blocks it.
    """
    ws = workspace or pathlib.Path.cwd()
    return may_demote(feature, target_status=target_status, workspace=ws)
