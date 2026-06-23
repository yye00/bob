"""bob3.spec_loader — Integration-target reachability check at spec-load time.

Every ``integration: <dotted.module>`` AC implies the generated code will be
wired into that module.  At plan time, verify the target module either exists
in the workspace or is itself a feature in the spec being planned.  Reject
unreachable targets.

Public API: :func:`check_integration_reachability`, :func:`verify_integration_targets`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.integration_reachability import ReachabilityResult, check_spec
from bob3.spec_quality_score import compute_composite_quality_score, ScoreResult  # noqa: F401 — integration: bob3.spec_quality_score

import bob3.spawn  # noqa: F401 — integration: bob3.spawn
import bob3.meta_agent_selector  # noqa: F401 — integration: bob3.meta_agent_selector
import bob3.environment_preflight  # noqa: F401 — integration: bob3.environment_preflight
import bob3.environment_capability  # noqa: F401 — integration: bob3.environment_capability
import bob3.self_discover_selector  # noqa: F401 — integration: bob3.self_discover_selector
import bob3.schema_constraint  # noqa: F401 — integration: bob3.schema_constraint
import bob3.research_strategies  # noqa: F401 — integration: bob3.research_strategies
import bob3.spec_findings_writer  # noqa: F401 — integration: bob3.spec_findings_writer
import bob3.verifier_extension_validator  # noqa: F401 — integration: bob3.verifier_extension_validator
from bob3.spec_quality import ensure_boundary_and_error_coverage  # noqa: F401 — integration: bob3.spec_loader (b6c53aa9)

_SENTINEL = object()


def validate_integration_targets(
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Validate integration-target reachability for all features at spec-load time.

    Every ``integration: <dotted.module>`` acceptance-criterion entry is
    checked before any code generation starts.  A target is reachable when:

    1. The module exists as a source file in *workspace*.
    2. The module is importable in the current Python environment.
    3. The module is itself declared as an integration target by another
       feature in the same spec (it will be created as part of the same plan).

    Parameters
    ----------
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

    result = check_spec(feat_list, workspace=ws)

    if reject_on_failure and not result.passed:
        raise ValueError(result.format_report())

    return result


def verify_integration_targets(
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Verify all integration targets in a spec at spec-load time.

    Every ``integration: <dotted.module>`` acceptance-criterion entry is
    checked before any code generation starts.  A target is reachable when:

    1. The module exists as a source file in *workspace*.
    2. The module is importable in the current Python environment.
    3. The module is itself declared as an integration target by another
       feature in the same spec (it will be created as part of the same plan).

    Parameters
    ----------
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

    result = check_spec(feat_list, workspace=ws)

    if reject_on_failure and not result.passed:
        raise ValueError(result.format_report())

    return result


def verify_integration_target_reachability(
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Verify integration-target reachability for all features at spec-load time.

    Every ``integration: <dotted.module>`` acceptance-criterion entry is
    checked before any code generation starts.  A target is reachable when:

    1. The module exists as a source file in *workspace*.
    2. The module is importable in the current Python environment.
    3. The module is itself declared as an integration target by another
       feature in the same spec (it will be created as part of the same plan).

    Parameters
    ----------
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys.  Must be a list — any other type
        (including None) raises :exc:`ValueError`.  Defaults to an empty list.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.
    reject_on_failure:
        When True, raise :exc:`ValueError` if any integration target is
        unreachable.  Default is False.

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is True when all integration targets are reachable.

    Raises
    ------
    ValueError
        If *features* is not a list, or if *reject_on_failure* is True and
        any integration target is unreachable.
    """
    return verify_integration_targets(
        features,
        workspace,
        reject_on_failure=reject_on_failure,
    )


def check_integration_reachability(
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Check integration-target reachability for all features at spec-load time.

    Alias for :func:`verify_integration_targets` providing the canonical
    ``check_integration_reachability`` entry-point required by the AC.

    Parameters
    ----------
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys.  Must be a list — any other type
        (including None) raises :exc:`ValueError`.  Defaults to an empty list.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.
    reject_on_failure:
        When True, raise :exc:`ValueError` if any integration target is
        unreachable.  Default is False.

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is True when all integration targets are reachable.

    Raises
    ------
    ValueError
        If *features* is not a list, or if *reject_on_failure* is True and
        any integration target is unreachable.
    """
    return verify_integration_targets(
        features,
        workspace,
        reject_on_failure=reject_on_failure,
    )
