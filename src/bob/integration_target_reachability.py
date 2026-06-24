"""bob.integration_target_reachability — Integration-target reachability check at spec-load time.

Every ``integration: <dotted.module>`` AC implies the generated code will be
wired into that module.  At plan time, verify the target module either exists
in the workspace or is itself a feature in the spec being planned.  Reject
unreachable targets.

Public API: :func:`verify_integration_target_reachable`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.integration_reachability import ReachabilityResult, check_spec, resolve_target

import bob.spec_loader  # noqa: F401 — integration: bob.spec_loader

_SENTINEL = object()


def verify_integration_target_reachable(
    module: str | None = None,
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Verify integration targets in a spec are reachable at spec-load time.

    Can be used in two modes:

    1. **Single-module mode**: Pass *module* to check one dotted module path.
    2. **Spec mode**: Pass *features* (a list of feature dicts) to check all
       ``integration: <dotted.module>`` ACs across the entire spec.

    A target is reachable when:

    1. The module exists as a source file in *workspace*.
    2. The module is importable in the current Python environment.
    3. The module is itself declared as an integration target by another
       feature in the same spec (it will be created as part of the same plan).

    Parameters
    ----------
    module:
        Single dotted module path to check.  When provided, only this module
        is verified.  When omitted, *features* is used.
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys.  Must be a list — any other type
        (including None) raises :exc:`ValueError`.  Defaults to an empty list.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.
    reject_on_failure:
        When True, raise :exc:`ValueError` if any integration target is
        unreachable.  Default is False (returns the result without raising).

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is True when all integration targets are reachable.
        Use ``result.format_report()`` for a structured error message.

    Raises
    ------
    ValueError
        If *features* is not a list, or if *reject_on_failure* is True and
        any integration target is unreachable.
    """
    if features is not _SENTINEL and not isinstance(features, list):
        raise ValueError(
            f"features must be a list, got {type(features).__name__!r}"
        )

    feat_list: list[dict[str, Any]] = [] if features is _SENTINEL else features  # type: ignore[assignment]
    ws = Path(workspace) if workspace is not None else Path.cwd()

    if module is not None:
        # Single-module check mode: synthesise a synthetic spec entry.
        synthetic_features = [
            {"name": module, "acceptance_criteria": [f"integration: {module}"]},
            *feat_list,
        ]
        result = check_spec(synthetic_features, workspace=ws)
    else:
        result = check_spec(feat_list, workspace=ws)

    if reject_on_failure and not result.passed:
        raise ValueError(result.format_report())

    return result
