"""Spec self-consistency — N-sample stability check pre-critic.

Public facade for the self-consistency checker.  Runs the spec extractor
N=3 times in parallel with different temperature/seeds, normalizes variants,
and computes a Jaccard stability_score over (AC.id, AC.behavior) tuples.

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Public API::

    from bob.spec_consistency_checker import (
        check_spec_stability,
        normalize_spec_variants,
        compute_jaccard_stability_score,
    )

    result = check_spec_stability(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
        n=3,
    )
    # result keys: stability_score, route, consensus, disagreeing_slots, majority_vote

Integration: bob.spec_critic — call check_spec_stability before critique_spec
to pre-filter low-stability specs and route them to clarification instead of
wasting the critic budget on unstable inputs.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.self_consistency import (
    _route_result,
    jaccard_stability,
    run_n_samples,
    _normalise_variant,
    _normalise_ac,
)

__all__ = [
    "check_spec_stability",
    "normalize_spec_variants",
    "compute_jaccard_stability_score",
]


def normalize_spec_variants(
    variants: list[list[dict[str, Any]]],
) -> list[tuple[tuple[str, str], ...]]:
    """Return a list of canonical (id, behavior) tuple-sets, one per variant.

    Each variant is normalized by stripping whitespace and collapsing
    internal runs of spaces in ``behavior`` fields.

    Parameters
    ----------
    variants:
        List of variant specs, each a list of AC dicts with ``id`` and
        ``behavior`` keys.

    Returns
    -------
    list of tuple of (id, behavior) tuples
        One sorted tuple per input variant, suitable for Jaccard comparison.

    Raises
    ------
    ValueError
        If ``variants`` is not a list, or any element is not a list.
    """
    if not isinstance(variants, list):
        raise ValueError(
            f"variants must be a list, got {type(variants).__name__!r}"
        )
    result = []
    for i, v in enumerate(variants):
        if not isinstance(v, list):
            raise ValueError(
                f"Each variant must be a list of dicts; variants[{i}] is "
                f"{type(v).__name__!r}"
            )
        result.append(tuple(sorted(_normalise_ac(ac) for ac in v)))
    return result


def compute_jaccard_stability_score(
    variants: list[list[dict[str, Any]]],
) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    For a single variant or when all variants are empty, returns 1.0.
    For multiple variants: |intersection| / |union| of their normalised AC sets.

    Parameters
    ----------
    variants:
        List of variant specs, each a list of AC dicts with ``id`` and
        ``behavior`` keys.  Must be non-empty.

    Returns
    -------
    float
        Stability score in [0.0, 1.0].

    Raises
    ------
    ValueError
        If ``variants`` is empty or not a list.
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


def check_spec_stability(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Any = None,
    _override_variants: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run the N-sample self-consistency stability check for a feature spec.

    Runs the spec extractor N times (default 3) with different seeds,
    normalizes the resulting variants, and computes a Jaccard stability score.
    Routes the result according to the score thresholds.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings.
    n:
        Number of extractor samples (default 3). Must be >= 1.
    variants_dir:
        Root directory for persisting variants.yaml.  Defaults to
        ``specs/`` relative to the current working directory.
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
        If ``acceptance_criteria`` is not a list, or ``n`` is not a positive int.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got "
            f"{type(acceptance_criteria).__name__!r}"
        )
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    if _override_variants is not None:
        score = jaccard_stability(_override_variants)
        result = _route_result(score=score, variants=_override_variants)
    else:
        from pathlib import Path

        vdir = Path(variants_dir) if variants_dir is not None else None
        result = run_n_samples(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            n=n,
            variants_dir=vdir,
        )

    return {
        "stability_score": result.stability_score,
        "route": result.route,
        "consensus": result.consensus,
        "disagreeing_slots": result.disagreeing_slots,
        "majority_vote": result.majority_vote,
    }
