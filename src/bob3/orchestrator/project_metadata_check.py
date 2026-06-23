"""Project metadata consistency checks for bob3 spawn/init lifecycle.

After spawn_next_generation.sh rsync-copies the parent directory, the
child bob3.db still contains the parent's project name and spec_path.
The functions here detect and fix those stale values, and are called
both by the spawn script (via ``bob3 init``) and by run_loop at startup.
"""

from __future__ import annotations

import logging
import os
import pathlib
import sqlite3
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class StaleSpecPathError(Exception):
    """Raised when spec_path in the projects table contains a pytest tmpdir prefix."""


class WorkspaceBasenameMissingError(Exception):
    """Raised when the current working directory has no resolvable basename."""


def run_bob3_init_post_rsync(
    workspace: pathlib.Path,
    current_gen: int,
    next_gen: int,
    *,
    venv_bin: Optional[pathlib.Path] = None,
) -> subprocess.CompletedProcess:
    """Execute ``bob3 init`` with the correct --name and --spec after rsync.

    spawn_next_generation.sh rsync-copies the parent DB, which retains the
    parent's project name and spec_path. This function re-runs init so the
    child bob3.db row reflects bob<NEXT> metadata.

    Args:
        workspace: The child generation workspace directory (bob<NEXT>).
        current_gen: The parent generation number (used to locate the spec).
        next_gen: The child generation number (used for --name).
        venv_bin: Path to .venv/bin directory; defaults to workspace/.venv/bin.

    Returns:
        CompletedProcess from subprocess.run.
    """
    if venv_bin is None:
        venv_bin = workspace / ".venv" / "bin"

    bob_cmd = str(venv_bin / f"bob{next_gen}")
    spec_path = workspace / "examples" / f"bootstrap_v0.{current_gen}.yaml"

    cmd = [bob_cmd, "init", str(workspace), "--name", f"bob{next_gen}"]
    if spec_path.exists():
        cmd.extend(["--spec", str(spec_path)])

    logger.info("Running post-rsync bob3 init: %s", " ".join(cmd))
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def verify_project_name_matches_dir(
    *,
    db_path: Optional[pathlib.Path] = None,
    workspace: Optional[pathlib.Path] = None,
) -> bool:
    """Return True iff projects.name equals the workspace directory basename.

    Args:
        db_path: Path to bob3.db; defaults to BOB3_DATABASE_PATH or cwd/bob3.db.
        workspace: Workspace directory; defaults to cwd.

    Returns:
        True if the stored project name matches the workspace basename.

    Raises:
        WorkspaceBasenameMissingError: When the resolved workspace has no basename.
    """
    if workspace is None:
        workspace = pathlib.Path.cwd()

    basename = workspace.name
    if not basename:
        raise WorkspaceBasenameMissingError(
            f"Workspace path {workspace!r} has no basename; cannot verify project name."
        )

    resolved_db = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(resolved_db))
    try:
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        if row is None:
            return False
        return row[0] == basename
    finally:
        conn.close()


def update_project_name_if_mismatch(
    *,
    db_path: Optional[pathlib.Path] = None,
    workspace: Optional[pathlib.Path] = None,
) -> bool:
    """Atomically UPDATE projects SET name=basename WHERE id=current if name is stale.

    Args:
        db_path: Path to bob3.db; defaults to BOB3_DATABASE_PATH or cwd/bob3.db.
        workspace: Workspace directory; defaults to cwd.

    Returns:
        True if an update was performed, False if name was already correct.

    Raises:
        WorkspaceBasenameMissingError: When the resolved workspace has no basename.
    """
    if workspace is None:
        workspace = pathlib.Path.cwd()

    basename = workspace.name
    if not basename:
        raise WorkspaceBasenameMissingError(
            f"Workspace path {workspace!r} has no basename; cannot update project name."
        )

    resolved_db = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(resolved_db))
    try:
        row = conn.execute("SELECT id, name FROM projects LIMIT 1").fetchone()
        if row is None:
            return False
        project_id, current_name = row
        if current_name == basename:
            return False
        conn.execute(
            "UPDATE projects SET name = ? WHERE id = ?",
            (basename, project_id),
        )
        conn.commit()
        logger.info(
            "Updated stale project name %r → %r (workspace: %s)",
            current_name,
            basename,
            workspace,
        )
        return True
    finally:
        conn.close()


def reject_pytest_tmpdir_in_spec_path(
    *,
    db_path: Optional[pathlib.Path] = None,
) -> None:
    """Raise StaleSpecPathError when spec_path contains a pytest tmpdir prefix.

    The bug: rsync copies the parent DB. If the parent ran tests that called
    ``bob3 init`` with a tempdir spec, the projects row ends up with
    spec_path = '/tmp/pytest-of-.../minimal.yaml'. This function detects that
    and raises so the caller can re-run init with the correct spec.

    Args:
        db_path: Path to bob3.db; defaults to BOB3_DATABASE_PATH or cwd/bob3.db.

    Raises:
        StaleSpecPathError: When spec_path contains "pytest-of-" substring.
    """
    resolved_db = _resolve_db_path(db_path)
    conn = sqlite3.connect(str(resolved_db))
    try:
        rows = conn.execute("SELECT name, spec_path FROM projects").fetchall()
    finally:
        conn.close()

    stale = [
        (name, sp)
        for name, sp in rows
        if sp and "pytest-of-" in sp
    ]
    if stale:
        names_and_paths = "; ".join(f"{n}: {sp}" for n, sp in stale)
        raise StaleSpecPathError(
            f"spec_path contains 'pytest-of-' tmpdir leak — re-run bob3 init with "
            f"correct --spec to fix. Affected rows: {names_and_paths}"
        )


def handle_missing_workspace_basename(
    workspace: Optional[pathlib.Path] = None,
) -> str:
    """Return the workspace basename or raise WorkspaceBasenameMissingError.

    Args:
        workspace: Directory path to inspect; defaults to cwd.

    Returns:
        The basename string when non-empty.

    Raises:
        WorkspaceBasenameMissingError: When basename is empty or None.
    """
    if workspace is None:
        workspace = pathlib.Path.cwd()

    basename = workspace.name
    if not basename:
        raise WorkspaceBasenameMissingError(
            f"cwd has no basename: {workspace!r}. "
            "This typically means the path is the filesystem root (/)."
        )
    return basename


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_db_path(db_path: Optional[pathlib.Path]) -> pathlib.Path:
    """Resolve a database path, falling back to env var then cwd/bob3.db."""
    if db_path is not None:
        return db_path
    env_path = os.environ.get("BOB3_DATABASE_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path.cwd() / "bob3.db"
