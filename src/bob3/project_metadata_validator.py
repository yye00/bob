"""Project metadata validator for bob3 spawn lifecycle.

After spawn_next_generation.sh rsync-copies the parent directory, the child
bob3.db still contains the parent's project name. This module provides:

- ``verify_project_name_matches_workspace``: checks whether ``projects.name``
  matches the workspace directory basename.
- ``reinit_stale_projects``: detects all rows with stale names and corrects them
  in-place via SQL UPDATE.

Both functions are safe to call at every startup — when metadata is already
correct they are fast no-ops.
"""

from __future__ import annotations

import logging
import os
import pathlib
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

_PYTEST_TMPDIR_MARKER = "pytest-of-"


def verify_project_name_matches_workspace(
    workspace: Optional[pathlib.Path | str | os.PathLike] = None,
    db_path: Optional[pathlib.Path | str | os.PathLike] = None,
) -> bool:
    """Return True iff ``projects.name`` matches the workspace directory basename.

    Connects to the database and reads the first row of the ``projects`` table.
    Returns ``True`` when the stored name exactly matches the workspace basename,
    ``False`` when they differ or when the table is empty.

    Safe to call at every startup — this is a read-only check with no side effects.

    Parameters
    ----------
    workspace:
        Workspace root directory.  Defaults to the current working directory.
        ``None`` and empty string are both treated as cwd.  Other invalid types
        raise ``ValueError``.
    db_path:
        Path to the bob3.db database.  Defaults to the ``BOB3_DATABASE_PATH``
        environment variable, or ``<workspace>/bob3.db`` when the env var is
        unset.

    Returns
    -------
    bool
        ``True`` if ``projects.name`` already matches the workspace basename,
        ``False`` if the name is stale or the table is empty.

    Raises
    ------
    ValueError
        When *workspace* is not a valid path type (str, bytes, os.PathLike, or None).
    """
    if workspace is not None and not isinstance(workspace, (str, bytes, os.PathLike)):
        raise ValueError(
            f"workspace must be a str, bytes, os.PathLike, or None; "
            f"got {type(workspace).__name__!r}"
        )

    resolved_workspace = _resolve_workspace(workspace)
    resolved_db = _resolve_db_path(db_path)
    workspace_basename = resolved_workspace.name

    try:
        conn = sqlite3.connect(str(resolved_db))
        try:
            row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        finally:
            conn.close()
    except Exception:
        return False

    if row is None:
        return False
    return row[0] == workspace_basename


def reinit_stale_projects(
    workspace: Optional[pathlib.Path | str | os.PathLike] = None,
    db_path: Optional[pathlib.Path | str | os.PathLike] = None,
) -> list[str]:
    """Detect and correct stale project names left by spawn_next_generation.sh.

    Reads every row in the ``projects`` table and updates the ``name`` column
    for any row whose stored name does not match the workspace directory basename.
    Also detects rows whose ``spec_path`` contains a pytest tmpdir prefix
    (``"pytest-of-"``), logging a warning for each.

    This function performs real SQL UPDATEs — it is not a dry-run.  It is safe
    to call repeatedly; rows already correct are left untouched.

    Parameters
    ----------
    workspace:
        Workspace root directory.  Defaults to the current working directory.
        ``None`` and empty string are both treated as cwd.  Other invalid types
        raise ``ValueError``.
    db_path:
        Path to the bob3.db database.  Defaults to the ``BOB3_DATABASE_PATH``
        environment variable, or ``<workspace>/bob3.db`` when the env var is
        unset.

    Returns
    -------
    list[str]
        A list of project IDs (as strings) whose names were corrected.
        Empty list when no updates were needed.

    Raises
    ------
    ValueError
        When *workspace* is not a valid path type (str, bytes, os.PathLike, or None).
    """
    if workspace is not None and not isinstance(workspace, (str, bytes, os.PathLike)):
        raise ValueError(
            f"workspace must be a str, bytes, os.PathLike, or None; "
            f"got {type(workspace).__name__!r}"
        )

    resolved_workspace = _resolve_workspace(workspace)
    resolved_db = _resolve_db_path(db_path)
    workspace_basename = resolved_workspace.name

    corrected_ids: list[str] = []

    try:
        conn = sqlite3.connect(str(resolved_db))
        try:
            rows = conn.execute(
                "SELECT id, name, spec_path FROM projects"
            ).fetchall()
        except sqlite3.OperationalError:
            conn.close()
            return corrected_ids

        try:
            for project_id, current_name, spec_path in rows:
                if current_name != workspace_basename:
                    conn.execute(
                        "UPDATE projects SET name = ? WHERE id = ?",
                        (workspace_basename, project_id),
                    )
                    corrected_ids.append(str(project_id))
                    logger.info(
                        "reinit_stale_projects: corrected project name %r → %r "
                        "(id=%s, workspace=%s)",
                        current_name,
                        workspace_basename,
                        project_id,
                        resolved_workspace,
                    )

                if spec_path and _PYTEST_TMPDIR_MARKER in spec_path:
                    logger.warning(
                        "reinit_stale_projects: stale pytest tmpdir in spec_path for "
                        "project %r — re-run 'bob3 init --spec <correct-spec>' to fix. "
                        "spec_path=%r",
                        current_name,
                        spec_path,
                    )

            if corrected_ids:
                conn.commit()
        finally:
            conn.close()

    except Exception as exc:
        logger.error("reinit_stale_projects: database error: %s", exc)

    return corrected_ids


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_workspace(
    workspace: Optional[pathlib.Path | str | os.PathLike],
) -> pathlib.Path:
    """Resolve the workspace to a Path, defaulting to cwd."""
    if workspace is None:
        return pathlib.Path.cwd()
    if isinstance(workspace, (str, bytes)) and not workspace:
        return pathlib.Path.cwd()
    return pathlib.Path(workspace)


def _resolve_db_path(
    db_path: Optional[pathlib.Path | str | os.PathLike],
) -> pathlib.Path:
    """Resolve a database path, falling back to env var then cwd/bob3.db."""
    if db_path is not None:
        return pathlib.Path(db_path)
    env_path = os.environ.get("BOB3_DATABASE_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path.cwd() / "bob3.db"
