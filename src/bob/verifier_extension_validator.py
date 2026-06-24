"""Verifier-extension AC validator.

Provides validate_ac_for_extension and enforce_ac_discipline — canonical entry
points for enforcing the AC discipline rule (F-779bebd4 / companion to
F-R7-592): features whose primary diff target is a verifier-extension module
MUST NOT carry behavior ACs.

All ACs for such features MUST be either:
  - structural ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")

Delegates to bob.spec_quality.spec_extractor for the enforcement logic and
the canonical VERIFIER_EXTENSION_MODULES registry.
"""

from __future__ import annotations

from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
    _is_verifier_extension,
)


def is_verifier_extension_feature(primary_diff_target: str) -> bool:
    """Return True when *primary_diff_target* is a verifier-extension module path.

    Used at spec-extraction time to gate the AC discipline rule enforcement.
    Returns False for empty or non-matching paths.

    Parameters
    ----------
    primary_diff_target:
        The primary file/module this feature changes.
    """
    return _is_verifier_extension(primary_diff_target)


def validate_acs_for_extension(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Validate ACs for verifier-extension features at spec-extraction time.

    Alias for :func:`validate_ac_for_extension` with plural name per AC discipline rule.

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

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    return validate_ac_for_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


def validate_ac_for_extension(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Validate ACs for verifier-extension features at spec-extraction time.

    When *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged with an empty
    ``demoted`` list and ``is_verifier_extension=False``.

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
    """Enforce AC discipline for verifier-extension features.

    Named entry point required by the AC discipline rule. Delegates to
    validate_ac_for_extension — rejects any AC line starting with 'behavior:'
    when *primary_diff_target* matches a VERIFIER_EXTENSION_MODULES path,
    replacing it with a skip note that suggests the structural or integration
    pytest form instead.

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

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list (invalid input type).
    """
    return validate_ac_for_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


__all__ = [
    "is_verifier_extension_feature",
    "validate_ac_for_extension",
    "validate_acs_for_extension",
    "enforce_ac_discipline",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
