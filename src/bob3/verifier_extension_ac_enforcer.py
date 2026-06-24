"""Verifier-extension AC discipline enforcer.

Enforces the rule that features whose primary diff target is a verifier-extension
module MUST NOT carry behavior ACs — the running verifier cannot check patterns
it doesn't yet know. All ACs for such features MUST be either:
  - structural  ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")

This module provides the canonical enforce_ac_discipline entry point that
integrates with bob3.spec_quality.spec_extractor.
"""

from __future__ import annotations

from bob3.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)


def enforce_verifier_extension_ac_discipline(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Enforce AC discipline for verifier-extension features at spec-extraction time.

    Canonical entry point (F-5376d57b).  When *primary_diff_target* resolves to
    a VERIFIER_EXTENSION_MODULES path, every AC line starting with 'behavior:'
    is rejected — replaced with a skip-with-note string — and a WARNING is emitted
    suggesting the structural or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier used in log messages for context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


def enforce_ac_discipline(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Enforce AC discipline for verifier-extension features at spec-extraction time.

    When *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier used in log messages for context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


def enforce_structural_integration_only(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Enforce that verifier-extension features express only structural or integration ACs.

    When *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier used in log messages for context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


def reject_behavior_acs(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    Canonical function name per AC discipline rule (F-424c7e60). When
    *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path, every
    AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier used in log messages for context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


__all__ = [
    "enforce_verifier_extension_ac_discipline",
    "enforce_ac_discipline",
    "enforce_structural_integration_only",
    "reject_behavior_acs",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
