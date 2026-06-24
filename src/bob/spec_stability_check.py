"""Spec self-consistency — N-sample stability check pre-critic.

Runs the spec extractor N=3 times in parallel with different temperature/seeds.
Normalizes variants and computes a Jaccard stability_score over (AC.id, AC.behavior)
tuples.

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Public API::

    from bob.spec_stability_check import run_stability_check, compute_jaccard_score
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bob.spec_extractor import extract_with_temperature
from bob.spec_quality.self_consistency import (
    SelfConsistencyResult,
    _route_result,
    jaccard_stability,
    _persist_variants,
)


@dataclass
class StabilityCheckResult:
    """Result of the N-sample self-consistency stability check."""

    stability_score: float
    route: str          # "clarification" | "critic" | "auto_accept"
    consensus: bool
    disagreeing_slots: list[tuple[str, str]]
    majority_vote: list[dict[str, str]]


def compute_jaccard_score(variants: list[list[dict[str, Any]]]) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    Parameters
    ----------
    variants:
        List of variant specs, each being a list of AC dicts with at least
        ``id`` and ``behavior`` keys. Must be non-empty; each element must
        be a list.

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
    if not isinstance(variants, list):
        raise ValueError(
            f"variants must be a list, got {type(variants).__name__!r}"
        )
    if len(variants) == 0:
        raise ValueError("variants must not be empty; pass at least one variant")
    for i, v in enumerate(variants):
        if not isinstance(v, list):
            raise ValueError(
                f"Each variant must be a list of dicts; variants[{i}] is {type(v).__name__!r}"
            )
    return jaccard_stability(variants)


def run_stability_check(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
) -> StabilityCheckResult:
    """Run the spec extractor N times and return a StabilityCheckResult.

    Integrates with bob.spec_extractor.extract_with_temperature to run N
    extraction rounds with different seeds. Normalizes variants and computes
    a Jaccard stability_score over (AC.id, AC.behavior) tuples.

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
        Number of extractor samples (default 3). Must be a positive integer.
    variants_dir:
        Root directory for persisting variants.yaml. Defaults to
        ``specs/`` relative to the current working directory.

    Returns
    -------
    StabilityCheckResult
        Contains ``stability_score``, ``route``, ``consensus``,
        ``disagreeing_slots``, and ``majority_vote``.

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
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    variants: list[list[dict[str, str]]] = []
    for seed in range(n):
        variant = extract_with_temperature(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            temperature=float(seed),
            seed=seed,
        )
        variants.append(variant)

    score = jaccard_stability(variants)

    internal_result: SelfConsistencyResult = _route_result(
        score=score,
        variants=variants,
    )

    if variants_dir is not None:
        vdir = Path(variants_dir)
    else:
        vdir = Path.cwd() / "specs"

    _persist_variants(feature_id, variants, internal_result, vdir)

    return StabilityCheckResult(
        stability_score=internal_result.stability_score,
        route=internal_result.route,
        consensus=internal_result.consensus,
        disagreeing_slots=internal_result.disagreeing_slots,
        majority_vote=internal_result.majority_vote,
    )


__all__ = [
    "StabilityCheckResult",
    "compute_jaccard_score",
    "run_stability_check",
]
