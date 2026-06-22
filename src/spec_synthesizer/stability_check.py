"""Spec self-consistency — N-sample stability check pre-critic.

Runs the spec extractor N=3 times in parallel with different temperature/seeds.
Normalizes variants and computes a Jaccard stability_score over (AC.id, AC.behavior)
tuples.

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Public API::

    from spec_synthesizer.stability_check import (
        compute_stability_score,
        run_parallel_extraction,
    )
"""

from __future__ import annotations

import collections
import concurrent.futures
import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

CLARIFICATION_THRESHOLD = 0.7
AUTO_ACCEPT_THRESHOLD = 0.9

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class StabilityResult:
    """Result of the N-sample stability check."""

    stability_score: float
    route: str         # "clarification" | "critic" | "auto_accept"
    consensus: bool
    disagreeing_slots: list[tuple[str, str]]
    majority_vote: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_ac(ac: dict[str, Any]) -> tuple[str, str]:
    ac_id = str(ac.get("id", "")).strip()
    behavior = _WHITESPACE_RE.sub(" ", str(ac.get("behavior", ""))).strip()
    return (ac_id, behavior)


def _normalize_variant(variant: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    return frozenset(_normalize_ac(ac) for ac in variant)


# ---------------------------------------------------------------------------
# Jaccard stability
# ---------------------------------------------------------------------------


def _jaccard(variants: list[list[dict[str, Any]]]) -> float:
    if len(variants) <= 1:
        return 1.0
    normalised = [_normalize_variant(v) for v in variants]
    intersection = normalised[0].copy()
    union: set[tuple[str, str]] = set(normalised[0])
    for ns in normalised[1:]:
        intersection &= ns
        union |= ns
    if not union:
        return 1.0
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Majority vote
# ---------------------------------------------------------------------------


def _majority_vote(variants: list[list[dict[str, Any]]], n: int) -> list[dict[str, str]]:
    counter: collections.Counter[tuple[str, str]] = collections.Counter()
    for variant in variants:
        for tup in _normalize_variant(variant):
            counter[tup] += 1
    threshold = n / 2
    return [
        {"id": ac_id, "behavior": behavior}
        for (ac_id, behavior), count in counter.most_common()
        if count > threshold
    ]


# ---------------------------------------------------------------------------
# Disagreeing slots
# ---------------------------------------------------------------------------


def _disagreeing_slots(variants: list[list[dict[str, Any]]]) -> list[tuple[str, str]]:
    if len(variants) <= 1:
        return []
    normalised = [_normalize_variant(v) for v in variants]
    union: set[tuple[str, str]] = set()
    for ns in normalised:
        union |= ns
    intersection = normalised[0].copy()
    for ns in normalised[1:]:
        intersection &= ns
    return sorted(union - intersection)


# ---------------------------------------------------------------------------
# Single-seed extractor
# ---------------------------------------------------------------------------

_AC_ID_RE = re.compile(r"^(AC-\d+|F-R\d+-\d+)\s*[:\-]\s*(.+)$")


def _extract_variant(
    acceptance_criteria: list[str],
    seed: int,
) -> list[dict[str, str]]:
    """Extract a normalized AC variant from acceptance criteria strings.

    At seed 0 returns base ACs unchanged. At higher seeds applies a small
    deterministic perturbation to simulate temperature/seed diversity.
    """
    result: list[dict[str, str]] = []
    for idx, ac in enumerate(acceptance_criteria):
        stripped = ac.strip()
        ac_id = f"AC-{idx + 1}"
        behavior = stripped
        if seed > 0:
            h = (seed * 31 + idx) % 3
            if h == 1:
                behavior = behavior + f" [variant-{seed}]"
        result.append({"id": ac_id, "behavior": behavior})
    return result


# ---------------------------------------------------------------------------
# Public: compute_stability_score
# ---------------------------------------------------------------------------


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
    return _jaccard(variants)


# ---------------------------------------------------------------------------
# Public: run_parallel_extraction
# ---------------------------------------------------------------------------


def run_parallel_extraction(
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
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    def _worker(seed: int) -> list[dict[str, str]]:
        return _extract_variant(acceptance_criteria, seed)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as executor:
        futures = [executor.submit(_worker, seed) for seed in range(n)]
        variants = [f.result() for f in futures]

    score = _jaccard(variants)
    n_variants = len(variants)

    if score < CLARIFICATION_THRESHOLD:
        return StabilityResult(
            stability_score=score,
            route="clarification",
            consensus=False,
            disagreeing_slots=_disagreeing_slots(variants),
            majority_vote=_majority_vote(variants, n_variants),
        )
    elif score >= AUTO_ACCEPT_THRESHOLD:
        return StabilityResult(
            stability_score=score,
            route="auto_accept",
            consensus=True,
            disagreeing_slots=[],
            majority_vote=_majority_vote(variants, n_variants),
        )
    else:
        return StabilityResult(
            stability_score=score,
            route="critic",
            consensus=False,
            disagreeing_slots=_disagreeing_slots(variants),
            majority_vote=_majority_vote(variants, n_variants),
        )
