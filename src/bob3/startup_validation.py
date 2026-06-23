"""Startup validation for bob3 project metadata after spawn_next_generation.sh rsync.

spawn_next_generation.sh rsync-copies the parent directory without re-running
``bob3 init``, so the child's bob3.db can retain stale ``projects.name`` (still
set to the parent generation name) and a stale ``spec_path`` (pointing at a
pytest tmpdir from the parent's test run).

This module provides ``validate_startup_metadata``, a thin wrapper that is called
during run_loop startup to detect and correct that stale state before the loop
begins dispatching features.

Usage
-----
::

    from bob3.startup_validation import validate_startup_metadata

    result = validate_startup_metadata()
    if result.name_was_stale:
        print(f"Corrected stale project name -> {result.corrected_name}")
    if result.spec_path_was_stale:
        print("spec_path contained a pytest tmpdir leak — re-run bob3 init --spec")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from bob3.run_loop import ProjectMetadataCheckResult, verify_project_metadata


def validate_startup_metadata(
    workspace: "str | os.PathLike[str] | None" = None,
    db_path: "str | os.PathLike[str] | None" = None,
) -> ProjectMetadataCheckResult:
    """Validate and correct stale project metadata at bob3 startup.

    Delegates to ``bob3.run_loop.verify_project_metadata`` which is the
    canonical implementation.  Called during run_loop startup to ensure the
    loop operates on accurate project metadata regardless of whether the
    workspace was freshly initialised or rsync-seeded from a parent generation.

    Parameters
    ----------
    workspace:
        Workspace root directory.  Defaults to the current working directory.
        ``None`` or empty string both resolve to ``Path.cwd()``.
    db_path:
        Path to the bob3.db database.  Defaults to the ``BOB3_DATABASE_PATH``
        environment variable or ``<workspace>/bob3.db``.

    Returns
    -------
    ProjectMetadataCheckResult
        Named tuple with fields:
        - name_was_stale: True if projects.name was corrected.
        - spec_path_was_stale: True if spec_path contained a pytest tmpdir.
        - corrected_name: The new name written, or None if no update was needed.
        - workspace_basename: The basename of the resolved workspace directory.

    Raises
    ------
    ValueError
        When workspace is not a valid path type (str, bytes, os.PathLike, or None).
    """
    return verify_project_metadata(workspace=workspace, db_path=db_path)


__all__ = [
    "validate_startup_metadata",
    "ProjectMetadataCheckResult",
]
