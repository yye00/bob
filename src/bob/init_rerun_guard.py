"""Guard that verifies and corrects stale project metadata after spawn.

spawn_next_generation.sh rsync-copies the parent bob.db without re-running
``bob init``. This leaves ``projects.name`` pointing at the parent generation
and ``spec_path`` possibly referencing a pytest tmpdir from the parent's test
run. This module provides ``verify_and_reinit_after_spawn`` as the canonical
startup guard that detects and corrects both issues.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)


def verify_and_reinit_after_spawn(
    workspace: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> "ProjectMetadataCheckResult":
    """Verify and correct stale project metadata left by spawn_next_generation.sh.

    Delegates to ``bob.run_loop.verify_project_metadata``, which:

    1. Checks whether ``projects.name`` matches the workspace directory basename.
    2. Corrects the name in-place (SQL UPDATE) if stale.
    3. Detects whether ``spec_path`` contains a pytest tmpdir prefix.

    Safe to call at every startup — when metadata is already correct the
    function is a fast no-op (two lightweight SQL reads, no writes).

    Parameters
    ----------
    workspace:
        Workspace root directory.  Defaults to current working directory.
        None and empty str are treated as cwd.  Other invalid types raise
        ``ValueError``.
    db_path:
        Path to the bob.db database.  Defaults to ``BOB_DATABASE_PATH``
        env var or ``<workspace>/bob.db``.

    Returns
    -------
    ProjectMetadataCheckResult
        Named tuple with fields ``name_was_stale``, ``spec_path_was_stale``,
        ``corrected_name``, and ``workspace_basename``.

    Raises
    ------
    ValueError
        When *workspace* is not a valid path type.
    """
    from bob.run_loop import verify_project_metadata, ProjectMetadataCheckResult  # noqa: F401

    resolved_workspace: Optional[pathlib.Path]
    if workspace is not None:
        if not isinstance(workspace, (str, bytes, os.PathLike)):
            raise ValueError(
                f"workspace must be a str, bytes, os.PathLike, or None; "
                f"got {type(workspace).__name__!r}"
            )
        resolved_workspace = pathlib.Path(workspace) if workspace else None
    else:
        resolved_workspace = None

    resolved_db: Optional[pathlib.Path] = (
        pathlib.Path(db_path) if db_path is not None else None
    )

    result = verify_project_metadata(
        workspace=resolved_workspace,
        db_path=resolved_db,
    )

    if result.name_was_stale:
        logger.info(
            "init_rerun_guard: corrected stale project name → %r "
            "(workspace: %s, spec_path_was_stale: %s)",
            result.corrected_name,
            resolved_workspace or pathlib.Path.cwd(),
            result.spec_path_was_stale,
        )
    if result.spec_path_was_stale:
        logger.warning(
            "init_rerun_guard: stale pytest tmpdir in spec_path — "
            "re-run 'bob init --spec <correct-spec>' to fix."
        )

    return result
