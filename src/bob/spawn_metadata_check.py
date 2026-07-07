"""Startup guard that corrects stale project metadata left by spawn.

``spawn_next_generation.sh`` rsync-copies the parent ``bob.db`` without
re-running ``bob init``. As a result the child's ``projects.name`` still
reflects the parent generation (e.g. ``bob96`` inside a ``bob97`` workspace)
and ``spec_path`` may point at a pytest tmpdir from the parent's test run.

This module provides two focused entry points used by ``bob.run_loop`` at
startup:

- :func:`verify_project_name_matches_workspace` — a read-only check that the
  stored project name equals the workspace directory basename.
- :func:`reinit_stale_project_metadata` — detect and correct that stale state
  in-place, returning the same :class:`~bob.run_loop.ProjectMetadataCheckResult`
  used across the metadata-check surface.

Both delegate to the shared logic in
``bob.orchestrator.project_metadata_check`` / ``bob.run_loop`` so the
correction rules live in one place.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from bob.run_loop import ProjectMetadataCheckResult

logger = logging.getLogger(__name__)

_PathArg = "str | os.PathLike[str] | None"


def _resolve_workspace(
    workspace: Optional[str | os.PathLike[str]],
) -> pathlib.Path:
    """Validate and resolve a workspace argument to a Path.

    ``None`` and empty string fall back to the current working directory.
    Any non-path type raises ``ValueError`` (never silently succeeds).
    """
    if workspace is not None and not isinstance(workspace, (str, bytes, os.PathLike)):
        raise ValueError(
            f"workspace must be a str, bytes, os.PathLike, or None; "
            f"got {type(workspace).__name__!r}"
        )
    if isinstance(workspace, (str, bytes)) and not workspace:
        return pathlib.Path.cwd()
    if workspace is None:
        return pathlib.Path.cwd()
    return pathlib.Path(os.fsdecode(workspace) if isinstance(workspace, bytes) else workspace)


def verify_project_name_matches_workspace(
    workspace: Optional[str | os.PathLike[str]] = None,
    db_path: Optional[str | os.PathLike[str]] = None,
) -> bool:
    """Return True iff ``projects.name`` equals the workspace directory basename.

    This is the read-only detection half of the spawn metadata guard. It never
    writes; use :func:`reinit_stale_project_metadata` to correct a mismatch.

    Args:
        workspace: Workspace root directory. Defaults to ``Path.cwd()``. ``None``
            and empty string are treated as cwd; other invalid types raise
            ``ValueError``.
        db_path: Path to ``bob.db``. Defaults to ``BOB_DATABASE_PATH`` env var
            or ``<workspace>/bob.db``.

    Returns:
        True when the stored project name matches the workspace basename; False
        when it is stale or there is no project row.

    Raises:
        ValueError: When ``workspace`` is not a valid path type.
    """
    from bob.orchestrator.project_metadata_check import verify_project_name_matches_dir

    resolved_workspace = _resolve_workspace(workspace)
    resolved_db = pathlib.Path(db_path) if db_path is not None else None

    return verify_project_name_matches_dir(
        db_path=resolved_db,
        workspace=resolved_workspace,
    )


def reinit_stale_project_metadata(
    workspace: Optional[str | os.PathLike[str]] = None,
    db_path: Optional[str | os.PathLike[str]] = None,
) -> ProjectMetadataCheckResult:
    """Detect and correct stale project metadata after ``spawn_next_generation.sh``.

    Steps:

    1. Correct ``projects.name`` in-place when it does not match the workspace
       basename (the parent-generation leak).
    2. Flag (via ``spec_path_was_stale``) when ``spec_path`` contains a pytest
       tmpdir prefix (``pytest-of-``), and log a warning telling the operator
       to re-run ``bob init --spec``.

    Safe to call at every startup — when metadata is already correct it is a
    fast no-op (lightweight SQL reads, no writes).

    Args:
        workspace: Workspace root directory. Defaults to ``Path.cwd()``. ``None``
            and empty string are treated as cwd; other invalid types raise
            ``ValueError``.
        db_path: Path to ``bob.db``. Defaults to ``BOB_DATABASE_PATH`` env var
            or ``<workspace>/bob.db``.

    Returns:
        ProjectMetadataCheckResult with ``name_was_stale``,
        ``spec_path_was_stale``, ``corrected_name`` and ``workspace_basename``.

    Raises:
        ValueError: When ``workspace`` is not a valid path type.
    """
    from bob.run_loop import verify_project_metadata

    # Validate before delegating so a bad type raises here consistently even if
    # run_loop's own validation ever diverges.
    resolved_workspace = _resolve_workspace(workspace)
    resolved_db = pathlib.Path(db_path) if db_path is not None else None

    result = verify_project_metadata(workspace=resolved_workspace, db_path=resolved_db)

    if result.name_was_stale:
        logger.info(
            "spawn_metadata_check: corrected stale project name → %r "
            "(workspace: %s, spec_path_was_stale: %s)",
            result.corrected_name,
            resolved_workspace,
            result.spec_path_was_stale,
        )
    if result.spec_path_was_stale:
        logger.warning(
            "spawn_metadata_check: stale pytest tmpdir in spec_path — "
            "re-run 'bob init --spec <correct-spec>' to fix."
        )

    return result
