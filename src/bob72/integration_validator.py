"""Integration-target reachability check at spec-load time.

Public API: :func:`validate_integration_targets`

For every ``integration: <dotted.module>`` acceptance-criterion entry in a
feature list, verifies the target module is reachable before any code is
generated:

  1. The module already exists as a source file in the workspace.
  2. OR the module is importable in the current Python environment.
  3. OR the module is declared as an integration target by another feature
     in the same spec (i.e., it will be created as part of the same plan).

Unreachable targets are reported as issues in the returned result object.

Pytest observability enforcement uses :mod:`bob12.superpowers` to ensure
sub-agents do not suppress pytest stdout during integration verification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.integration_reachability import (  # noqa: F401 – re-exported
    ReachabilityResult,
    check_spec,
)
import bob12.superpowers as _superpowers  # noqa: F401 – integration wiring


def validate_integration_targets(
    features: list[dict[str, Any]],
    workspace: Path | str | None = None,
) -> ReachabilityResult:
    """Check every ``integration: <dotted.module>`` AC in *features*.

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
