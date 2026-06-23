"""Spec self-consistency — N-sample stability check pre-critic (F-5cdc0a7d).

Runs the spec extractor N=3 times in parallel with different temperature/seeds.
Normalizes variants and computes a Jaccard stability_score over (AC.id, AC.behavior)
tuples.

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Public API::

    from bob3.spec_stability_checker import (
        compute_stability_score,
        run_parallel_extractions,
    )
"""

from __future__ import annotations

from typing import Any

from spec_synthesizer.stability_check import (
    compute_stability_score as _compute_stability_score,
    run_parallel_extraction as _run_parallel_extraction,
    StabilityResult,
    _extract_variant,
)
from bob3.spec_quality.self_consistency import (
    jaccard_stability as _jaccard_stability,
    _route_result,
)


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
        If ``variants`` is empty, not a list, or contains non-list elements.
    """
    return _compute_stability_score(variants)


def run_parallel_extractions(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    _override_variants: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run the spec extractor N times in parallel and return a stability result dict.

    Runs the spec extractor N times with different seeds to simulate
    temperature/seed diversity. Normalizes variants and computes a Jaccard
    stability_score over (AC.id, AC.behavior) tuples. Routes the result
    based on the score.

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
    _override_variants:
        For testing only — bypass the extractor and supply pre-built variants.

    Returns
    -------
    dict with keys:
        - ``stability_score`` (float): Jaccard stability score in [0.0, 1.0]
        - ``route`` (str): one of ``"clarification"``, ``"critic"``, ``"auto_accept"``
        - ``consensus`` (bool): True when route == "auto_accept"
        - ``disagreeing_slots`` (list): (id, behavior) pairs that differ across variants
        - ``majority_vote`` (list): AC dicts from majority vote

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    if _override_variants is not None:
        if not isinstance(acceptance_criteria, list):
            raise ValueError(
                f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
            )
        score = _jaccard_stability(_override_variants)
        internal = _route_result(score=score, variants=_override_variants)
        return {
            "stability_score": internal.stability_score,
            "route": internal.route,
            "consensus": internal.consensus,
            "disagreeing_slots": internal.disagreeing_slots,
            "majority_vote": internal.majority_vote,
        }

    result: StabilityResult = _run_parallel_extraction(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
    )
    return {
        "stability_score": result.stability_score,
        "route": result.route,
        "consensus": result.consensus,
        "disagreeing_slots": result.disagreeing_slots,
        "majority_vote": result.majority_vote,
    }


def extract_spec_variants(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
) -> list[list[dict[str, Any]]]:
    """Run the spec extractor N times with different seeds and return the variants.

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
    list of list of dicts
        N extracted AC variant lists, each being a list of AC dicts with
        ``id`` and ``behavior`` keys.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    return [_extract_variant(acceptance_criteria, seed) for seed in range(n)]


def compute_jaccard_score(variants: list[list[dict[str, Any]]]) -> float:
    """Compute the Jaccard stability score — alias for compute_stability_score.

    Parameters
    ----------
    variants:
        List of variant specs, each a list of AC dicts with ``id`` and
        ``behavior`` keys. Must be non-empty; each element must be a list.

    Returns
    -------
    float
        Stability score in [0.0, 1.0].

    Raises
    ------
    ValueError
        If ``variants`` is empty, not a list, or contains non-list elements.
    """
    return compute_stability_score(variants)


def run_stability_check(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    _override_variants: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run the N-sample stability check and return a result dict.

    Alias for run_parallel_extractions with the canonical name required by
    the feature acceptance criteria.

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
    _override_variants:
        For testing only — bypass the extractor and supply pre-built variants.

    Returns
    -------
    dict with keys:
        - ``stability_score`` (float)
        - ``route`` (str): one of ``"clarification"``, ``"critic"``,
          ``"auto_accept"``
        - ``consensus`` (bool)
        - ``disagreeing_slots`` (list)
        - ``majority_vote`` (list)

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a
        positive integer.
    """
    return run_parallel_extractions(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
        _override_variants=_override_variants,
    )


__all__ = [
    "compute_jaccard_score",
    "compute_stability_score",
    "extract_spec_variants",
    "run_parallel_extractions",
    "run_stability_check",
]
