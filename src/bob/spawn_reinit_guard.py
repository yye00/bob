"""Startup guard that detects and corrects stale project metadata after spawn.

spawn_next_generation.sh rsync-copies the parent bob.db, which retains the
parent's projects.name and may have a stale spec_path from a pytest tmpdir.
This module provides verify_project_metadata, called at run_loop startup to
ensure the loop operates on accurate metadata.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from bob.run_loop import ProjectMetadataCheckResult

logger = logging.getLogger(__name__)


def verify_project_metadata(
    workspace: Optional[pathlib.Path | str | os.PathLike] = None,
    db_path: Optional[pathlib.Path | str | os.PathLike] = None,
) -> ProjectMetadataCheckResult:
    """Detect and correct stale project metadata left by spawn_next_generation.sh.

    Checks whether projects.name matches the workspace directory basename and
    corrects it in-place if stale. Also detects whether spec_path contains a
    pytest tmpdir prefix ("pytest-of-") indicating a leak from parent test runs.

    Safe to call at every startup — when metadata is already correct, it is a
    fast no-op (two lightweight SQL reads, no writes).

    Args:
        workspace: Workspace root directory. Defaults to cwd. Must be None, str,
            bytes, or os.PathLike; other types raise ValueError.
        db_path: Path to the bob.db database. Defaults to the
            BOB_DATABASE_PATH env var or <workspace>/bob.db.

    Returns:
        ProjectMetadataCheckResult with fields:
        - name_was_stale: True when the name row was updated.
        - spec_path_was_stale: True when spec_path contained a pytest tmpdir leak.
        - corrected_name: The new name written, or None if no update.
        - workspace_basename: The basename of the resolved workspace.

    Raises:
        ValueError: When workspace is not a valid path type.
    """
    from bob.orchestrator.project_metadata_check import (
        StaleSpecPathError,
        update_project_name_if_mismatch,
        reject_pytest_tmpdir_in_spec_path,
    )

    if workspace is not None and not isinstance(workspace, (str, bytes, os.PathLike)):
        raise ValueError(
            f"workspace must be a str, bytes, os.PathLike, or None; "
            f"got {type(workspace).__name__!r}"
        )

    if workspace is not None and isinstance(workspace, (str, bytes)) and not workspace:
        resolved_workspace = pathlib.Path.cwd()
    else:
        resolved_workspace = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()

    resolved_db: Optional[pathlib.Path]
    if db_path is not None:
        resolved_db = pathlib.Path(db_path)
    else:
        env_path = os.environ.get("BOB_DATABASE_PATH")
        resolved_db = pathlib.Path(env_path) if env_path else None

    workspace_basename = resolved_workspace.name

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
            "spawn_reinit_guard: stale pytest tmpdir in spec_path — "
            "re-run 'bob init --spec <correct-spec>' to fix. Detail: %s",
            exc,
        )

    if name_was_stale:
        logger.info(
            "spawn_reinit_guard: corrected stale project name → %r "
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
