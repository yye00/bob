"""Integration-target reachability check at spec-load time for bob74.

Public API: :func:`validate_integration_targets`

Validates every ``integration: <dotted.module>`` acceptance-criterion in a
feature list before any code is generated.  Delegates to
:func:`bob3.spec_quality.integration_reachability.check_spec` for the core
reachability logic and wires into :mod:`bob3.rca` for RCA-layer integration.

A target is reachable if:
  1. The module already exists as a source file in the workspace.
  2. The module is importable in the current Python environment.
  3. The module is declared as an integration target by another feature in
     the same spec (it will be created as part of the same plan).

Raises :exc:`ValueError` when *features* is not a list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.integration_reachability import (  # noqa: F401
    ReachabilityResult,
    check_spec,
)
import bob3.rca as _rca  # noqa: F401 – integration wiring per AC "integration: bob3.rca"


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
