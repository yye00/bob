"""Spec self-consistency — N-sample stability check pre-critic (hippy).

Cheap pre-critic filter based on the Self-Consistency pattern (ICLR 2023).
Runs the spec extractor N=3 times with different seeds, normalises the
variants, and computes a Jaccard ``stability_score`` over
``(AC.id, AC.behavior)`` tuples.

Routing table
-------------
stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
0.7 ≤ score < 0.9       → route = "critic"          (standard critic path)
stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Results are persisted to ``<variants_dir>/<feature_id>/variants.yaml``.

Public API::

    from hippy.spec_self_consistency import (
        compute_stability_score,
        run_self_consistency_check,
    )
"""

from __future__ import annotations

import collections
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from hippy.spec_extractor import extract_variant

logger = logging.getLogger(__name__)

CLARIFICATION_THRESHOLD = 0.7   # below → route to F-R7-456
AUTO_ACCEPT_THRESHOLD = 0.9     # at or above → auto-accept with consensus:true

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class SelfConsistencyResult:
    """Result of the N-sample self-consistency check."""

    stability_score: float
    route: str                                  # clarification | critic | auto_accept
    consensus: bool                             # True only when route == auto_accept
    disagreeing_slots: list[tuple[str, str]]    # (AC.id, AC.behavior) that differ
    majority_vote: list[dict[str, str]]         # majority-vote AC list


def _normalise_ac(ac: dict[str, Any]) -> tuple[str, str]:
    ac_id = str(ac.get("id", "")).strip()
    behavior = _WHITESPACE_RE.sub(" ", str(ac.get("behavior", ""))).strip()
    return (ac_id, behavior)


def _normalise_variant(variant: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    return frozenset(_normalise_ac(ac) for ac in variant)


def _validate_variants(variants: Any) -> None:
    """Raise ValueError when *variants* is not a non-empty list of variant lists."""
    if not isinstance(variants, list):
        raise ValueError(
            f"variants must be a list of variant lists, got {type(variants).__name__}"
        )
    if len(variants) == 0:
        raise ValueError("variants must be a non-empty list")
    for i, variant in enumerate(variants):
        if not isinstance(variant, list):
            raise ValueError(
                f"variant at index {i} must be a list of AC dicts, "
                f"got {type(variant).__name__}"
            )


def compute_stability_score(variants: list[list[dict[str, Any]]]) -> float:
    """Compute the Jaccard stability score over ``(AC.id, AC.behavior)`` tuples.

    For a single variant the score is ``1.0`` (perfect stability). For
    multiple variants it is ``|intersection| / |union|`` of their normalised
    AC sets; an empty union also yields ``1.0``.

    Parameters
    ----------
    variants:
        Non-empty list of variant specs; each variant is a list of AC dicts
        with at least ``id`` and ``behavior`` keys.

    Returns
    -------
    float
        Stability score in ``[0.0, 1.0]``.

    Raises
    ------
    ValueError
        If ``variants`` is not a non-empty list of lists.
    """
    _validate_variants(variants)

    if len(variants) == 1:
        return 1.0

    normalised = [_normalise_variant(v) for v in variants]
    intersection = set(normalised[0])
    union: set[tuple[str, str]] = set(normalised[0])
    for ns in normalised[1:]:
        intersection &= ns
        union |= ns

    if not union:
        return 1.0
    return len(intersection) / len(union)


def _majority_vote(
    variants: list[list[dict[str, Any]]], n: int
) -> list[dict[str, str]]:
    counter: collections.Counter[tuple[str, str]] = collections.Counter()
    for variant in variants:
        for tup in _normalise_variant(variant):
            counter[tup] += 1
    threshold = n / 2
    return [
        {"id": ac_id, "behavior": behavior}
        for (ac_id, behavior), count in counter.most_common()
        if count > threshold
    ]


def _disagreeing_slots(
    variants: list[list[dict[str, Any]]],
) -> list[tuple[str, str]]:
    if len(variants) <= 1:
        return []
    normalised = [_normalise_variant(v) for v in variants]
    union: set[tuple[str, str]] = set()
    for ns in normalised:
        union |= ns
    intersection = set(normalised[0])
    for ns in normalised[1:]:
        intersection &= ns
    return sorted(union - intersection)


def _route_result(
    *, score: float, variants: list[list[dict[str, Any]]]
) -> SelfConsistencyResult:
    n = len(variants)
    if score < CLARIFICATION_THRESHOLD:
        return SelfConsistencyResult(
            stability_score=score,
            route="clarification",
            consensus=False,
            disagreeing_slots=_disagreeing_slots(variants),
            majority_vote=_majority_vote(variants, n),
        )
    if score >= AUTO_ACCEPT_THRESHOLD:
        return SelfConsistencyResult(
            stability_score=score,
            route="auto_accept",
            consensus=True,
            disagreeing_slots=[],
            majority_vote=_majority_vote(variants, n),
        )
    return SelfConsistencyResult(
        stability_score=score,
        route="critic",
        consensus=False,
        disagreeing_slots=_disagreeing_slots(variants),
        majority_vote=_majority_vote(variants, n),
    )


def _persist_variants(
    feature_id: str,
    variants: list[list[dict[str, Any]]],
    result: SelfConsistencyResult,
    variants_dir: Path,
) -> Path:
    out_dir = variants_dir / feature_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "variants.yaml"

    payload: dict[str, Any] = {
        "feature_id": feature_id,
        "stability_score": round(result.stability_score, 6),
        "route": result.route,
        "consensus": result.consensus,
        "variants": [
            [{"id": ac["id"], "behavior": ac["behavior"]} for ac in v]
            for v in variants
        ],
    }
    if result.disagreeing_slots:
        payload["disagreeing_slots"] = [
            {"id": s[0], "behavior": s[1]} for s in result.disagreeing_slots
        ]
    if result.majority_vote:
        payload["majority_vote"] = result.majority_vote

    out_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
    logger.debug("Persisted variants to %s", out_path)
    return out_path


def run_self_consistency_check(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
) -> SelfConsistencyResult:
    """Run the spec extractor N times and return a routed SelfConsistencyResult.

    Parameters
    ----------
    feature_id:
        Unique feature identifier (used as directory name under ``variants_dir``).
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings.
    n:
        Number of parallel extractor samples (default 3). Must be a positive int.
    variants_dir:
        Root directory for persisting ``variants.yaml``. Defaults to
        ``specs/`` relative to the current working directory.

    Returns
    -------
    SelfConsistencyResult

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list, or ``n`` is not a positive
        integer.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got "
            f"{type(acceptance_criteria).__name__}"
        )
    # bool is a subclass of int; reject it explicitly along with non-ints.
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"n must be a positive integer, got {type(n).__name__}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    if variants_dir is None:
        variants_dir = Path.cwd() / "specs"
    variants_dir = Path(variants_dir)

    variants: list[list[dict[str, str]]] = [
        extract_variant(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            seed=seed,
        )
        for seed in range(n)
    ]

    # compute_stability_score requires a non-empty list; n>=1 guarantees that.
    score = compute_stability_score(variants)
    logger.info(
        "hippy self-consistency stability_score=%.3f feature=%s n=%d",
        score, feature_id, n,
    )

    result = _route_result(score=score, variants=variants)
    _persist_variants(feature_id, variants, result, variants_dir)
    logger.info(
        "hippy self-consistency route=%s consensus=%s feature=%s",
        result.route, result.consensus, feature_id,
    )
    return result
