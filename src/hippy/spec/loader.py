"""hippy.spec.loader — spec loading wired to spec-load-time reachability checks.

Every ``integration: <dotted.module>`` AC implies the generated code will be
wired into that module.  This loader integrates the reachability check so that
a spec is validated at load time: unreachable integration targets are rejected
before any code generation begins.

Public API:
  :func:`load_spec`                    — parse a spec dict and validate targets.
  :func:`validate_spec_reachability`   — run the reachability check on a spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hippy.spec.reachability import (
    ReachabilityResult,
    check_integration_reachability,
)


def validate_spec_reachability(
    features: Any,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Validate integration-target reachability for a spec's *features*.

    Thin loader-level wrapper over
    :func:`hippy.spec.reachability.check_integration_reachability` so callers
    that only hold a loader reference can run the spec-load-time check.

    Raises
    ------
    ValueError
        If *features* is not a list, or if *reject_on_failure* is ``True`` and
        any integration target is unreachable.
    """
    return check_integration_reachability(
        features=features,
        workspace=workspace,
        reject_on_failure=reject_on_failure,
    )


def load_spec(
    spec: dict[str, Any],
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = True,
) -> dict[str, Any]:
    """Load *spec* and validate its integration targets at spec-load time.

    Parameters
    ----------
    spec:
        A spec dict with a ``features`` key mapping to a list of feature dicts.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.
    reject_on_failure:
        When ``True`` (the default at load time), raise :exc:`ValueError` if any
        integration target is unreachable.

    Returns
    -------
    dict[str, Any]
        The validated *spec* (returned unchanged when all targets reachable).

    Raises
    ------
    ValueError
        If *spec* is not a dict, or if reachability validation fails while
        *reject_on_failure* is ``True``.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")

    features = spec.get("features", [])
    validate_spec_reachability(
        features,
        workspace=workspace,
        reject_on_failure=reject_on_failure,
    )
    return spec
