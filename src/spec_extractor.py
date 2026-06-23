"""Spec self-consistency — N-sample stability check pre-critic.

Public façade exposing ``run_n_sample_stability_check`` and
``compute_jaccard_stability_score`` for the spec self-consistency pipeline.

Delegates to ``bob3.spec_quality.spec_extractor`` and
``bob3.spec_quality.self_consistency`` for the actual implementation.

Integration: bob3.spec_quality.spec_extractor

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (consensus:true)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.self_consistency import (
    SelfConsistencyResult,
    jaccard_stability,
    normalize_variant,
    run_n_samples,
)


def run_n_sample_stability_check(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
) -> SelfConsistencyResult:
    """Run the spec extractor N times in parallel and return a routed SelfConsistencyResult.

    Parameters
    ----------
    feature_id:
        Unique feature identifier (used as directory under ``specs/``).
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings.
    n:
        Number of parallel extractor samples (default 3). Must be >= 1.
    variants_dir:
        Root directory for persisting ``variants.yaml``. Defaults to
        ``specs/`` relative to the current working directory.

    Returns
    -------
    SelfConsistencyResult
        Contains ``stability_score``, ``route``, ``consensus``,
        ``disagreeing_slots``, and ``majority_vote``.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list or ``n`` is not a positive integer.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    return run_n_samples(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
        variants_dir=variants_dir,
    )


def compute_jaccard_stability_score(variants: list[list[dict[str, Any]]]) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    For a single variant or empty inner variants the score is 1.0 (perfect
    stability).  For multiple variants: |intersection| / |union| of the
    normalised AC sets.

    Parameters
    ----------
    variants:
        List of variant specs, each being a list of AC dicts with at least
        ``id`` and ``behavior`` keys. Must be non-empty.

    Returns
    -------
    float
        Stability score in [0.0, 1.0].

    Raises
    ------
    ValueError
        If ``variants`` is empty or not a list, or if any element is not a list.
    """
    if not isinstance(variants, list):
        raise ValueError(
            f"variants must be a list, got {type(variants).__name__!r}"
        )
    if len(variants) == 0:
        raise ValueError("variants must not be empty; pass at least one variant")
    for i, v in enumerate(variants):
        if not isinstance(v, list):
            raise ValueError(
                f"Each variant must be a list of dicts; variants[{i}] is "
                f"{type(v).__name__!r}"
            )
    return jaccard_stability(variants)


def normalize_variants(
    variants: list[list[dict[str, Any]]],
) -> list[tuple[tuple[str, str], ...]]:
    """Normalize a list of AC variants into canonical sorted tuple form.

    Each variant is a list of AC dicts with ``id`` and ``behavior`` keys.
    Returns a list of sorted tuples for deterministic Jaccard comparison.

    Parameters
    ----------
    variants:
        List of AC variant lists.

    Returns
    -------
    list of tuple
        Each element is a sorted tuple of (id, behavior) pairs.
    """
    return [normalize_variant(v) for v in variants]


def compute_jaccard_stability(variants: list[list[dict[str, Any]]]) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    Alias for ``compute_jaccard_stability_score`` satisfying the AC:
    ``Function defined: spec_extractor.compute_jaccard_stability``.

    Parameters
    ----------
    variants:
        List of variant specs, each a list of AC dicts with at least
        ``id`` and ``behavior`` keys. Must be non-empty.

    Returns
    -------
    float
        Stability score in [0.0, 1.0].

    Raises
    ------
    ValueError
        If ``variants`` is empty, not a list, or any element is not a list.
    """
    return compute_jaccard_stability_score(variants)


def run_parallel_extraction(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
) -> SelfConsistencyResult:
    """Run the spec extractor N times in parallel and return a routed SelfConsistencyResult.

    Alias for ``run_n_sample_stability_check`` satisfying the AC:
    ``Function defined: spec_extractor.run_parallel_extraction``.

    Parameters
    ----------
    feature_id:
        Unique feature identifier (used as directory under ``specs/``).
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings.
    n:
        Number of parallel extractor samples (default 3). Must be >= 1.
    variants_dir:
        Root directory for persisting ``variants.yaml``.

    Returns
    -------
    SelfConsistencyResult
        Contains ``stability_score``, ``route``, ``consensus``,
        ``disagreeing_slots``, and ``majority_vote``.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list or ``n`` is not a positive integer.
    """
    return run_n_sample_stability_check(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
        variants_dir=variants_dir,
    )
