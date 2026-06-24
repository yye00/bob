"""Startup check: re-run project metadata verification after spawn.

spawn_next_generation.sh rsync-copies the parent bob.db without re-running
``bob init``. This leaves ``projects.name`` pointing at the parent generation
and ``spec_path`` possibly referencing a pytest tmpdir from the parent's test run.

This module provides two canonical entry points:

- ``verify_project_metadata``: detect and correct stale metadata at startup.
- ``reinit_after_spawn``: alias that makes the spawn-triggered nature explicit.

Both delegate to ``bob.run_loop.verify_project_metadata`` so the correction
logic stays in one place.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)


def verify_project_metadata(
    workspace: Optional[str | os.PathLike] = None,
    db_path: Optional[str | os.PathLike] = None,
) -> "ProjectMetadataCheckResult":
    """Detect and correct stale project metadata left by spawn_next_generation.sh.

    spawn_next_generation.sh rsync-copies the parent DB without re-running
    ``bob init``, so ``projects.name`` still reflects the parent generation
    and ``spec_path`` may point to a pytest tmpdir from the parent's test run.

    This function:
    1. Checks whether ``projects.name`` matches the workspace directory basename.
    2. Corrects the name in-place (SQL UPDATE) if it is stale.
    3. Detects whether ``spec_path`` contains a pytest tmpdir prefix
       (``"pytest-of-"``) and sets ``spec_path_was_stale`` accordingly.

    Safe to call at every startup — when metadata is already correct, it is a
    fast no-op (two lightweight SQL reads, no writes).

    Args:
        workspace: Workspace root directory. Defaults to ``Path.cwd()``.
            None and empty str are treated as cwd. Other invalid types raise
            ``ValueError``.
        db_path: Path to the bob.db database. Defaults to the
            ``BOB_DATABASE_PATH`` env var or ``<workspace>/bob.db``.

    Returns:
        ProjectMetadataCheckResult with fields:
        - ``name_was_stale``: True when the name row was updated.
        - ``spec_path_was_stale``: True when spec_path contained a pytest tmpdir.
        - ``corrected_name``: The new name written, or None if no update.
        - ``workspace_basename``: The basename of the resolved workspace.

    Raises:
        ValueError: When workspace is not a valid path type.
    """
    from bob.run_loop import verify_project_metadata as _run_loop_verify, ProjectMetadataCheckResult  # noqa: F401

    resolved_workspace: Optional[pathlib.Path]
    if workspace is not None and not isinstance(workspace, (str, bytes, os.PathLike)):
        raise ValueError(
            f"workspace must be a str, bytes, os.PathLike, or None; "
            f"got {type(workspace).__name__!r}"
        )

    if isinstance(workspace, (str, bytes)) and not workspace:
        resolved_workspace = None  # run_loop treats empty as cwd
    elif workspace is not None:
        resolved_workspace = pathlib.Path(workspace)
    else:
        resolved_workspace = None

    resolved_db: Optional[pathlib.Path] = (
        pathlib.Path(db_path) if db_path is not None else None
    )

    result = _run_loop_verify(workspace=resolved_workspace, db_path=resolved_db)

    if result.name_was_stale:
        logger.info(
            "init_re_run: corrected stale project name → %r "
            "(workspace: %s, spec_path_was_stale: %s)",
            result.corrected_name,
            resolved_workspace or pathlib.Path.cwd(),
            result.spec_path_was_stale,
        )
    if result.spec_path_was_stale:
        logger.warning(
            "init_re_run: stale pytest tmpdir in spec_path — "
            "re-run 'bob init --spec <correct-spec>' to fix."
        )

    return result


def reinit_after_spawn(
    workspace: Optional[str | os.PathLike] = None,
    db_path: Optional[str | os.PathLike] = None,
) -> "ProjectMetadataCheckResult":
    """Correct stale project metadata after spawn_next_generation.sh.

    Explicit spawn-triggered alias for ``verify_project_metadata``.  Call this
    from spawn hooks to make the intent clear: the parent DB was rsync-copied
    and this call brings the child's metadata into sync.

    Args:
        workspace: Workspace root directory.  Defaults to ``Path.cwd()``.
        db_path: Path to the bob.db database.  See ``verify_project_metadata``.

    Returns:
        ProjectMetadataCheckResult — same shape as ``verify_project_metadata``.

    Raises:
        ValueError: When workspace is not a valid path type.
    """
    return verify_project_metadata(workspace=workspace, db_path=db_path)
