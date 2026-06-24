"""Integration-target reachability check at spec-load time for bob75.

Every ``integration: <dotted.module>`` AC implies the generated code will be
wired into that module.  At plan time, verify the target module either exists
in the workspace or is itself a feature in the spec being planned.  Reject
unreachable targets.

Public API: :func:`verify_integration_target`

A target is reachable if:
  1. The module exists as a source file in the workspace.
  2. The module is importable in the current Python environment.
  3. The module is declared as an integration target by another feature in
     the same spec (it will be created as part of the same plan).

Raises :exc:`ValueError` when *features* is not a list (when passed as the
``features`` keyword argument).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.integration_reachability import (  # noqa: F401
    ReachabilityResult,
    check_spec,
)
import bob75.spec_loader as _spec_loader  # noqa: F401 — integration: spec_loader

_SENTINEL = object()


def verify_integration_target(
    module: str | None = None,
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
) -> ReachabilityResult:
    """Verify integration target reachability at spec-load time.

    Can be called in two modes:

    **Single-module mode** — pass *module* to check one dotted module name:

    .. code-block:: python

        result = verify_integration_target("bob.rca", workspace=Path("/project"))

    **Spec mode** — pass *features* to check all integration ACs in a spec:

    .. code-block:: python

        result = verify_integration_target(features=[...], workspace=Path("/project"))

    Parameters
    ----------
    module:
        Dotted module path to verify (single-module mode).  Mutually
        exclusive with *features*.
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys (spec mode).  Must be a list — passing
        any other type (including None) raises :exc:`ValueError`.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is True when all checked integration targets are
        reachable.  Use ``result.format_report()`` for a structured error
        message.

    Raises
    ------
    ValueError
        If *features* is provided but is not a list.
    """
    ws = Path(workspace) if workspace is not None else Path.cwd()

    if features is not _SENTINEL and not isinstance(features, list):
        raise ValueError(
            f"features must be a list, got {type(features).__name__!r}"
        )

    # Normalise: _SENTINEL means "not passed" → treat as empty list in spec mode
    feat_list: list[dict[str, Any]] = [] if features is _SENTINEL else features  # type: ignore[assignment]

    if module is not None:
        # Single-module mode: wrap in a synthetic feature for check_spec.
        synthetic_features: list[dict[str, Any]] = [
            {
                "name": module,
                "acceptance_criteria": [f"integration: {module}"],
            }
        ]
        # Merge with any additionally provided spec features for sibling-module resolution.
        return check_spec(synthetic_features + feat_list, workspace=ws)

    # Spec mode: check all integration ACs in all provided features.
    return check_spec(feat_list, workspace=ws)
