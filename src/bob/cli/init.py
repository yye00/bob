"""bob CLI init integration helpers.

Exposes the project-metadata startup checks that are wired into
``bob init`` (the ``init`` Click command in ``bob.cli``).  After
spawn_next_generation.sh rsync-copies the parent directory, the child
bob.db retains stale project name and spec_path values.  The helpers
here are called from the init command to detect and fix that state.
"""

from __future__ import annotations

from bob.orchestrator.project_metadata_check import (
    StaleSpecPathError,
    WorkspaceBasenameMissingError,
    handle_missing_workspace_basename,
    reject_pytest_tmpdir_in_spec_path,
    run_bob_init_post_rsync,
    update_project_name_if_mismatch,
    verify_project_name_matches_dir,
)

__all__ = [
    "StaleSpecPathError",
    "WorkspaceBasenameMissingError",
    "handle_missing_workspace_basename",
    "reject_pytest_tmpdir_in_spec_path",
    "run_bob_init_post_rsync",
    "update_project_name_if_mismatch",
    "verify_project_name_matches_dir",
]
