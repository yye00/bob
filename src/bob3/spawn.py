"""bob3.spawn — spawn lifecycle helpers for project metadata verification.

After spawn_next_generation.sh rsync-copies the parent directory, the child
bob3.db retains stale project name and spec_path values.  This module exposes
``verify_project_metadata`` as the canonical entry point for detecting and
correcting that state.  The same function is also exposed via ``bob3.run_loop``
for startup-check wiring.

AC-form validation at planning time
------------------------------------
``validate_acceptance_criteria`` is re-exported here so that the spawn layer
can enforce AC grammar before persisting features.  Integrating the validator
here prevents the v.13 class of parser bugs (trailing prose in pytest: ACs,
parenthetical Function defined: descriptions) from reaching the database.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from bob3.ac_form_validator import validate_acceptance_criteria  # noqa: F401
from bob3.orchestrator.spawn_retry import (  # noqa: F401
    classify_exit,
    spawn_with_retry,
)
from bob3.run_loop import ProjectMetadataCheckResult, verify_project_metadata

__all__ = [
    "ProjectMetadataCheckResult",
    "verify_project_metadata",
    "re_init_after_spawn",
    "reinit_after_spawn",
    "validate_acceptance_criteria",
    "classify_exit",
    "spawn_with_retry",
]


def re_init_after_spawn(
    workspace: Optional[pathlib.Path] = None,
    db_path: Optional[pathlib.Path] = None,
) -> ProjectMetadataCheckResult:
    """Re-initialize project metadata after spawn_next_generation.sh rsync.

    spawn_next_generation.sh copies the parent DB via rsync without re-running
    ``bob3 init``, leaving ``projects.name`` set to the parent generation name
    and ``spec_path`` potentially pointing to a pytest tmpdir.

    This function detects and corrects stale project metadata at startup:

    1. Checks whether ``projects.name`` matches the workspace directory basename.
    2. Corrects the name in-place (SQL UPDATE) when stale.
    3. Detects whether ``spec_path`` contains a pytest tmpdir prefix ("pytest-of-")
       and returns ``spec_path_was_stale=True`` when found.

    Boundary cases:
    - Empty/missing DB (no projects rows): returns a no-op result without crashing.
    - ``workspace`` is ``None``: defaults to the current working directory.

    Args:
        workspace: Workspace root directory. Defaults to ``Path.cwd()``.
        db_path: Path to the bob3.db database. Defaults to the
            ``BOB3_DATABASE_PATH`` environment variable or
            ``<workspace>/bob3.db``.

    Returns:
        ProjectMetadataCheckResult with corrected metadata fields.

    Raises:
        ValueError: When ``workspace`` is provided but resolves to a path with
            no basename (e.g. the filesystem root ``/``).
    """
    resolved_workspace = workspace if workspace is not None else pathlib.Path.cwd()

    if not resolved_workspace.name:
        raise ValueError(
            f"workspace path {resolved_workspace!r} has no basename; "
            "cannot determine the expected project name. "
            "Provide a non-root directory path."
        )

    return verify_project_metadata(workspace=resolved_workspace, db_path=db_path)


#: Canonical alias: "Function defined: bob3.spawn.reinit_after_spawn"
reinit_after_spawn = re_init_after_spawn
