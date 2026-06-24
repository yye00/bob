"""Spec extractor public API — bob.spec_extractor.

Provides extract_with_temperature: run the spec extractor once with a specific
temperature/seed, returning a list of normalised AC dicts.

This module wraps the internal extraction logic from
bob.spec_quality.self_consistency._extract_variant to expose a stable public
API for the N-sample stability check pre-critic.

Public API::

    from bob.spec_extractor import extract_with_temperature
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.self_consistency import _extract_variant
from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)


def reject_behavior_ac_for_verifier_extension(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    When *primary_diff_target* matches a VERIFIER_EXTENSION_MODULES path, every
    AC line starting with 'behavior:' is rejected — replaced with a skip-with-note
    string — and a WARNING is emitted suggesting the structural or integration
    pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec. Must be a list.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier for log context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list.
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


def reject_behavior_acs_for_verifier_extensions(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    Canonical AC discipline entry point (F-92221849). When *primary_diff_target*
    includes a VERIFIER_EXTENSION_MODULES path, every AC line starting with
    'behavior:' is rejected — replaced with a skip-with-note string — and a
    WARNING is emitted suggesting the structural or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec. Must be a list.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier for log context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list.
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


def reject_behavior_ac_in_verifier_extension(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    Alias for reject_behavior_ac_for_verifier_extension. When *primary_diff_target*
    matches a VERIFIER_EXTENSION_MODULES path, every AC line starting with
    'behavior:' is rejected and a WARNING is emitted suggesting the structural or
    integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec. Must be a list.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier for log context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list.
    """
    return reject_behavior_ac_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


def extract_with_temperature(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    temperature: float = 0.0,
    seed: int = 0,
) -> list[dict[str, str]]:
    """Extract a normalised AC variant using a specific temperature/seed.

    Runs the spec extractor once with the given seed to simulate temperature
    diversity. Seed 0 returns the base (unperturbed) ACs; higher seeds apply
    small deterministic perturbations.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings. Must be a list (may be empty).
    temperature:
        Sampling temperature (informational; currently mapped to seed for
        deterministic simulation). Unused in the deterministic extractor.
    seed:
        Integer seed offset (0 = base variant, >0 = perturbed variants).

    Returns
    -------
    list of dict
        Extracted AC variant: list of dicts with ``id`` and ``behavior`` keys.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    return _extract_variant(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        seed=seed,
    )


__all__ = [
    "extract_with_temperature",
    "reject_behavior_ac_for_verifier_extension",
    "reject_behavior_acs_for_verifier_extensions",
    "reject_behavior_ac_in_verifier_extension",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
