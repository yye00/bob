"""Spawn-next-generation metadata verification for bob.

When spawn_next_generation.sh rsync-copies the parent directory, the child's
bob.db retains the parent's ``projects.name`` and may have a stale ``spec_path``
pointing at a pytest tmpdir from the parent's test run.

This module exposes ``verify_project_metadata`` as the canonical entry point for
detecting and correcting that stale state.  It is a thin wrapper around
``bob.run_loop.verify_project_metadata`` so callers can import from either
location.

Integration with run_loop
-------------------------
``bob.run_loop`` calls ``verify_project_metadata`` at startup so the loop always
operates on accurate project metadata regardless of whether the workspace was
freshly initialised or rsync-seeded from a parent generation.

Usage
-----
::

    from bob.spawn_next_generation import verify_project_metadata

    result = verify_project_metadata()
    if result.name_was_stale:
        print(f"Corrected stale project name -> {result.corrected_name}")
    if result.spec_path_was_stale:
        print("spec_path contained a pytest tmpdir leak — re-run bob init --spec")
"""

from __future__ import annotations

import os
import pathlib
import subprocess
from typing import Optional

from bob.run_loop import ProjectMetadataCheckResult, verify_project_metadata as _verify
from bob.seed_inheritance import apply_parent_generation_data, SeedInheritanceResult
from bob.parent_gen_db import inherit_parent_status


def reinit_after_spawn(
    workspace: "str | os.PathLike[str]",
    current_gen: int,
    next_gen: int,
    *,
    venv_bin: Optional[pathlib.Path] = None,
) -> subprocess.CompletedProcess:
    """Re-run ``bob init`` after spawn_next_generation.sh rsync to fix stale metadata.

    spawn_next_generation.sh rsync-copies the parent directory, including
    bob.db, which retains the parent's ``projects.name`` and may have a
    stale ``spec_path`` from a pytest tmpdir. Calling this function re-runs
    ``bob init`` with the correct ``--name`` and optional ``--spec`` so the
    child DB row reflects the new generation.

    Parameters
    ----------
    workspace:
        The child generation workspace directory (bob<next_gen>).
    current_gen:
        The parent generation number (used to locate the bootstrap spec file).
    next_gen:
        The child generation number (used for ``--name bob<next_gen>``).
    venv_bin:
        Path to the venv bin directory; defaults to
        ``<workspace>/.venv/bin``.

    Returns
    -------
    subprocess.CompletedProcess
        The completed process from running ``bob<next_gen> init``.
    """
    from bob.orchestrator.project_metadata_check import run_bob_init_post_rsync

    resolved_workspace = pathlib.Path(workspace)
    return run_bob_init_post_rsync(
        workspace=resolved_workspace,
        current_gen=current_gen,
        next_gen=next_gen,
        venv_bin=venv_bin,
    )


#: Canonical alias required by AC: "Function defined: bob.spawn_next_generation.reinit_project_after_spawn"
reinit_project_after_spawn = reinit_after_spawn

#: Canonical alias required by AC: "Function defined: bob.spawn_next_generation.re_init_after_spawn"
re_init_after_spawn = reinit_after_spawn


def verify_project_metadata(
    workspace: "str | os.PathLike[str] | None" = None,
    db_path: "str | os.PathLike[str] | None" = None,
) -> ProjectMetadataCheckResult:
    """Detect and correct stale project metadata left by spawn_next_generation.sh.

    spawn_next_generation.sh rsync-copies the parent DB without re-running
    ``bob init``, so ``projects.name`` still reflects the parent generation
    and ``spec_path`` may point to a pytest tmpdir from the parent's test run.

    Delegates to ``bob.run_loop.verify_project_metadata`` which is the
    authoritative implementation wired into the run_loop startup path.

    Parameters
    ----------
    workspace:
        Workspace root directory.  Defaults to current working directory.
        None and empty string both resolve to cwd.  Any other non-path type
        raises ``ValueError``.
    db_path:
        Path to the bob.db database.  Defaults to ``BOB_DATABASE_PATH`` env
        var or ``<workspace>/bob.db``.

    Returns
    -------
    ProjectMetadataCheckResult
        Named tuple with fields:
        - ``name_was_stale``: True when ``projects.name`` was updated.
        - ``spec_path_was_stale``: True when ``spec_path`` contained a pytest
          tmpdir leak.
        - ``corrected_name``: The new name written, or None if no update needed.
        - ``workspace_basename``: The basename of the resolved workspace.

    Raises
    ------
    ValueError
        When workspace is not a valid path type (str, bytes, os.PathLike, or None).
    """
    return _verify(workspace=workspace, db_path=db_path)


__all__ = [
    "reinit_after_spawn",
    "re_init_after_spawn",
    "reinit_project_after_spawn",
    "verify_project_metadata",
    "ProjectMetadataCheckResult",
    "apply_parent_generation_data",
    "SeedInheritanceResult",
    "inherit_parent_status",
]
