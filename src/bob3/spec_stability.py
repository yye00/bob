"""Spec self-consistency — N-sample stability check pre-critic.

Public API module for the spec self-consistency stability pipeline.

Runs the spec extractor N=3 times in parallel with different temperature/seeds.
Normalizes variants and computes a Jaccard stability_score over (AC.id, AC.behavior)
tuples.

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Public API::

    from bob3.spec_stability import (
        compute_stability_score,
        extract_and_normalize_variants,
        extract_spec_variants,
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_synthesizer.stability_check import (
    compute_stability_score as _compute_stability_score,
    run_parallel_extraction as _run_parallel_extraction,
    _normalize_variant as _sc_normalize_variant,
    StabilityResult,
)
from bob3.spec_quality.self_consistency import (
    _extract_variant as _sc_extract_variant,
)


def extract_spec_variants(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
) -> list[list[dict[str, Any]]]:
    """Extract N spec variants by running the extractor with different seeds.

    Runs the spec extractor N times with deterministic seed offsets to simulate
    temperature/seed diversity. Each variant is a list of AC dicts with ``id``
    and ``behavior`` keys.

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
    n:
        Number of extraction samples (default 3). Must be a positive integer.

    Returns
    -------
    list of list of dict
        N extracted variants, each a list of AC dicts.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(
            f"n must be a positive integer >= 1, got {n!r}"
        )

    variants: list[list[dict[str, Any]]] = []
    for seed in range(n):
        variant = _sc_extract_variant(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            seed=seed,
        )
        variants.append(variant)
    return variants


def extract_and_normalize_variants(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
) -> list[tuple[tuple[str, str], ...]]:
    """Extract N spec variants and normalize them into canonical (id, behavior) tuples.

    Combines extraction and normalization: runs the spec extractor N times with
    different seeds, then normalizes each variant into a sorted tuple of
    ``(id, behavior)`` string pairs with whitespace collapsed.

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
    n:
        Number of extraction samples (default 3). Must be a positive integer.

    Returns
    -------
    list of tuple of (str, str) pairs
        N normalized variants, each a sorted tuple of ``(id, behavior)`` pairs.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    raw_variants = extract_spec_variants(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
    )
    return [_sc_normalize_variant(variant) for variant in raw_variants]


def compute_stability_score(variants: list[list[dict[str, Any]]]) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    Parameters
    ----------
    variants:
        List of variant specs, each being a list of AC dicts with at least
        ``id`` and ``behavior`` keys. Must be non-empty.

    Returns
    -------
    float
        Stability score in [0.0, 1.0]. Returns 1.0 for a single variant or
        when all variants are empty.

    Raises
    ------
    ValueError
        If ``variants`` is empty or not a list.
    """
    return _compute_stability_score(variants)


def run_parallel_extractions(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
) -> StabilityResult:
    """Run the spec extractor N times in parallel and return a StabilityResult.

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
    n:
        Number of parallel extractor samples (default 3). Must be >= 1.

    Returns
    -------
    StabilityResult
        Contains ``stability_score``, ``route``, ``consensus``,
        ``disagreeing_slots``, and ``majority_vote``.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    return _run_parallel_extraction(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
    )
