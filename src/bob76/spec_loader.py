"""bob76.spec_loader — spec loading with integration-target reachability gate.

Wraps the base spec-loading logic with a call to
:func:`bob76.integration_check.validate_integration_targets` so that every
``integration: <dotted.module>`` AC is validated before any code generation
starts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.integration_reachability import ReachabilityResult


def load_and_verify(
    features: list[dict[str, Any]],
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Load *features* and verify all integration targets are reachable.

    Parameters
    ----------
    features:
        List of feature dicts, each with ``name`` and ``acceptance_criteria``.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.
    reject_on_failure:
        When True, raise :exc:`ValueError` if any integration target is
        unreachable.  Default is False (returns the result without raising).

    Returns
    -------
    ReachabilityResult
        Reachability check result.  ``result.passed`` is True when all
        integration targets are reachable.
    """
    from bob76.integration_check import validate_integration_targets

    return validate_integration_targets(
        features=features,
        workspace=workspace,
        reject_on_failure=reject_on_failure,
    )
