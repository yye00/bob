"""Spec self-consistency — N-sample stability check pre-critic (F-R7-467).

Public facade for the self-consistency pipeline in
``bob3.spec_quality.self_consistency``.

Runs the spec extractor N=3 times in parallel with different temperature/seeds.
Normalises variants and computes a Jaccard stability_score over (AC.id, AC.behavior)
tuples.

Routing semantics:
  stability_score < 0.7   → route = "clarification"  (F-R7-456, disagreeing slots cited)
  0.7 ≤ score < 0.9       → route = "critic"
  stability_score ≥ 0.9   → route = "auto_accept"     (majority-vote spec, consensus:true)

Public API::

    from bob3.spec_self_consistency_n_sample_stability_check_pre_critic import (
        spec_self_consistency_n_sample_stability_check_pre_critic,
    )

    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
        n=3,
    )
    # result keys: stability_score, route, consensus, disagreeing_slots, majority_vote
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from bob3.spec_quality.self_consistency import (
    SelfConsistencyResult,
    jaccard_stability,
    run_n_samples,
    _route_result,
)


def spec_self_consistency_n_sample_stability_check_pre_critic(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
    _override_variants: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run the N-sample self-consistency stability check for a feature spec.

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
        Number of extractor samples (default 3).
    variants_dir:
        Root directory for persisting variants.yaml. Defaults to
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
    """
    if _override_variants is not None:
        score = jaccard_stability(_override_variants)
        result: SelfConsistencyResult = _route_result(
            score=score,
            variants=_override_variants,
        )
    else:
        result = run_n_samples(
            feature_id=feature_id,
            name=name,
            description=description,
            acceptance_criteria=acceptance_criteria,
            n=n,
            variants_dir=variants_dir,
        )

    return {
        "stability_score": result.stability_score,
        "route": result.route,
        "consensus": result.consensus,
        "disagreeing_slots": result.disagreeing_slots,
        "majority_vote": result.majority_vote,
    }
