"""Integration-target reachability check at spec-load time.

Public API: :func:`check_reachability`

For every ``integration: <dotted.module>`` acceptance-criterion entry in a
feature list, verifies the target module is reachable before any code is
generated:

  1. The module already exists as a source file in the workspace.
  2. OR the module is importable in the current Python environment.
  3. OR the module is declared as an integration target by another feature
     in the same spec (i.e., it will be created as part of the same plan).

Unreachable targets are reported as issues in the returned result object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.integration_reachability import (
    ReachabilityResult,
    check_spec,
)


def check_reachability(
    features: list[dict[str, Any]],
    workspace: Path | str | None = None,
) -> ReachabilityResult:
    """Check every ``integration: <dotted.module>`` AC in *features*.

    For each integration target, the check passes if ANY of:
      - The module exists as a source file in *workspace*.
      - The module is importable in the current Python environment.
      - The module is itself declared as an integration target in another
        feature in the same spec (i.e., it will be created).

    Parameters
    ----------
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys.  Must be a list — passing any other
        type raises :exc:`ValueError`.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is True when all integration targets are reachable.
        Use ``result.format_report()`` for a structured error message.

    Raises
    ------
    ValueError
        If *features* is not a list.
    """
    if not isinstance(features, list):
        raise ValueError(
            f"features must be a list, got {type(features).__name__!r}"
        )
    return check_spec(features, workspace=workspace)
