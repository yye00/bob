"""Startup validator that detects and corrects stale project metadata after spawn.

spawn_next_generation.sh rsync-copies the parent bob.db, which retains the
parent's projects.name and may have a stale spec_path from a pytest tmpdir.
This module provides the canonical verify_project_metadata function that is
called at run_loop startup to ensure the loop operates on accurate metadata.

The function delegates to bob.orchestrator.project_metadata_check helpers
and re-exports ProjectMetadataCheckResult from bob.run_loop so callers can
use either import path.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from bob.run_loop import ProjectMetadataCheckResult, verify_project_metadata as _run_loop_verify

logger = logging.getLogger(__name__)


def verify_project_metadata(
    workspace: Optional[str | os.PathLike] = None,
    db_path: Optional[str | os.PathLike] = None,
) -> ProjectMetadataCheckResult:
    """Verify and correct stale project metadata left by spawn_next_generation.sh.

    spawn_next_generation.sh rsync-copies the parent DB without re-running
    ``bob init``, so projects.name may still reflect the parent generation
    and spec_path may point to a pytest tmpdir from the parent's test run.

    This function:

    1. Checks whether projects.name matches the workspace directory basename.
    2. Corrects the name in-place (SQL UPDATE) if it is stale.
    3. Detects whether spec_path contains a pytest tmpdir prefix and sets
       spec_path_was_stale accordingly.

    Safe to call at every startup — when metadata is already correct it is a
    fast no-op (two lightweight SQL reads, no writes).

    Args:
        workspace: Workspace root directory. Defaults to cwd. Must be None,
            str, bytes, or os.PathLike; other types raise ValueError.
        db_path: Path to the bob.db database. Defaults to BOB_DATABASE_PATH
            env var or <workspace>/bob.db.

    Returns:
        ProjectMetadataCheckResult with fields:
        - name_was_stale: True when the name row was updated.
        - spec_path_was_stale: True when spec_path contained a pytest tmpdir.
        - corrected_name: The new name written, or None if no update needed.
        - workspace_basename: The basename of the resolved workspace.

    Raises:
        ValueError: When workspace is not a valid path type.
    """
    return _run_loop_verify(workspace=workspace, db_path=db_path)


__all__ = ["verify_project_metadata", "ProjectMetadataCheckResult"]
