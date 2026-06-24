"""Startup check that detects and corrects stale project metadata after spawn.

spawn_next_generation.sh rsync-copies the parent bob3.db, which retains the
parent's projects.name and may have a stale spec_path from a pytest tmpdir.
This module provides the canonical function for detecting and correcting that
state at run_loop startup.

The function delegates to the existing helpers in
``bob3.orchestrator.project_metadata_check`` and wraps them in the same
``ProjectMetadataCheckResult`` named tuple used by ``run_loop.verify_project_metadata``.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from bob3.run_loop import ProjectMetadataCheckResult

logger = logging.getLogger(__name__)


def bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
    workspace: Optional[pathlib.Path] = None,
    db_path: Optional[pathlib.Path] = None,
) -> ProjectMetadataCheckResult:
    """Detect and correct stale project metadata left by spawn_next_generation.sh.

    spawn_next_generation.sh rsync-copies the parent DB without re-running
    ``bob3 init``, so ``projects.name`` still reflects the parent generation
    and ``spec_path`` may point to a pytest tmpdir from the parent's test run.

    This function:

    1. Checks whether ``projects.name`` matches the workspace directory basename.
    2. Corrects the name in-place (SQL UPDATE) if it is stale.
    3. Detects whether ``spec_path`` contains a pytest tmpdir prefix
       ("pytest-of-") and sets ``spec_path_was_stale`` accordingly.

    It is safe to call at every startup — when metadata is already correct, it
    is a fast no-op (two lightweight SQL reads, no writes).

    Args:
        workspace: Workspace root directory. Defaults to ``Path.cwd()``.
        db_path: Path to the bob3.db database. Defaults to the
            ``BOB3_DATABASE_PATH`` environment variable or
            ``<workspace>/bob3.db``.

    Returns:
        ProjectMetadataCheckResult with fields:
        - ``name_was_stale``: True when the name row was updated.
        - ``spec_path_was_stale``: True when spec_path contained a pytest
          tmpdir leak.
        - ``corrected_name``: The new name written, or None if no update.
        - ``workspace_basename``: The basename of the resolved workspace.
    """
    from bob3.orchestrator.project_metadata_check import (
        StaleSpecPathError,
        update_project_name_if_mismatch,
        reject_pytest_tmpdir_in_spec_path,
    )

    resolved_workspace = workspace if workspace is not None else pathlib.Path.cwd()
    workspace_basename = resolved_workspace.name

    resolved_db: Optional[pathlib.Path]
    if db_path is not None:
        resolved_db = db_path
    else:
        env_path = os.environ.get("BOB3_DATABASE_PATH")
        resolved_db = pathlib.Path(env_path) if env_path else None

    name_was_stale = update_project_name_if_mismatch(
        db_path=resolved_db,
        workspace=resolved_workspace,
    )
    corrected_name = workspace_basename if name_was_stale else None

    spec_path_was_stale = False
    try:
        reject_pytest_tmpdir_in_spec_path(db_path=resolved_db)
    except StaleSpecPathError as exc:
        spec_path_was_stale = True
        logger.warning(
            "bob3_init_re_run check: stale pytest tmpdir in spec_path — "
            "re-run 'bob3 init --spec <correct-spec>' to fix. Detail: %s",
            exc,
        )

    if name_was_stale:
        logger.info(
            "bob3_init_re_run: corrected stale project name → %r "
            "(workspace: %s, spec_path_was_stale: %s)",
            corrected_name,
            resolved_workspace,
            spec_path_was_stale,
        )

    return ProjectMetadataCheckResult(
        name_was_stale=name_was_stale,
        spec_path_was_stale=spec_path_was_stale,
        corrected_name=corrected_name,
        workspace_basename=workspace_basename,
    )
