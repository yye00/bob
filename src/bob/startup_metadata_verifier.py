"""Startup verifier for project metadata consistency after spawn_next_generation.sh.

After spawn_next_generation.sh rsync-copies the parent directory, the child
bob.db still contains the parent's project name and may have a stale
spec_path from a pytest tmpdir. This module exposes ``verify_project_metadata``
as the canonical startup check entry point called by run_loop.

The implementation delegates to the helpers in
``bob.orchestrator.project_metadata_check`` and produces the same
``ProjectMetadataCheckResult`` named tuple used throughout run_loop.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from bob.run_loop import ProjectMetadataCheckResult

logger = logging.getLogger(__name__)


def verify_project_metadata(
    workspace: str | os.PathLike | None = None,
    db_path: str | os.PathLike | None = None,
) -> ProjectMetadataCheckResult:
    """Verify and fix stale project metadata left by spawn_next_generation.sh.

    spawn_next_generation.sh rsync-copies the parent DB without re-running
    ``bob init``, so ``projects.name`` still reflects the parent generation
    and ``spec_path`` may point to a pytest tmpdir from the parent's test run.

    This function:

    1. Validates the workspace argument type.
    2. Checks whether ``projects.name`` matches the workspace directory basename.
    3. Corrects the name in-place (SQL UPDATE) if it is stale.
    4. Detects whether ``spec_path`` contains a pytest tmpdir prefix
       ("pytest-of-") and sets ``spec_path_was_stale`` accordingly.

    It is safe to call at every run_loop startup — when metadata is already
    correct, it is a fast no-op (two lightweight SQL reads, no writes).

    Parameters
    ----------
    workspace:
        Workspace root directory. Defaults to current working directory.
        Must be ``None``, a ``str``, or an ``os.PathLike``. An empty string
        is treated as the current working directory. Invalid types (e.g. int,
        list, dict) raise ``ValueError``.
    db_path:
        Path to the bob.db database. Defaults to the ``BOB_DATABASE_PATH``
        environment variable or ``<workspace>/bob.db``.

    Returns
    -------
    ProjectMetadataCheckResult
        Named tuple with fields:
        - ``name_was_stale``: True when the name row was updated.
        - ``spec_path_was_stale``: True when spec_path contained a pytest
          tmpdir leak.
        - ``corrected_name``: The new name written, or None if no update.
        - ``workspace_basename``: The basename of the resolved workspace.

    Raises
    ------
    ValueError
        When workspace is not a valid path type (str, bytes, os.PathLike, or None).
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

    if isinstance(workspace, (str, bytes)) and not workspace:
        resolved_workspace = pathlib.Path.cwd()
    elif workspace is None:
        resolved_workspace = pathlib.Path.cwd()
    else:
        resolved_workspace = pathlib.Path(workspace)

    workspace_basename = resolved_workspace.name

    resolved_db: Optional[pathlib.Path]
    if db_path is not None:
        resolved_db = pathlib.Path(db_path)
    else:
        env_path = os.environ.get("BOB_DATABASE_PATH")
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
            "startup_metadata_verifier: stale pytest tmpdir in spec_path — "
            "re-run 'bob init --spec <correct-spec>' to fix. Detail: %s",
            exc,
        )

    if name_was_stale:
        logger.info(
            "startup_metadata_verifier: corrected stale project name → %r "
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
