"""Readiness seed sweep for bob3.

Seeds readiness_score for every ready feature that still sits at 0.0,
breaking the chicken-and-egg deadlock where fresh features can never be
claimed because claim gate requires readiness_score >= threshold, yet
assess_feature_confidence is only called after a feature is claimed.

This module is the canonical entry point for AC:
  'File exists: src/bob3/readiness_seed_sweep.py'
  'Function defined: bob3.readiness_seed_sweep.seed_readiness_for_zero_features'
"""

from __future__ import annotations

__all__ = ["seed_readiness_for_zero_features"]


def seed_readiness_for_zero_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Must be called at the TOP of each run-loop iteration so freshly-promoted
    features (status='ready', readiness_score==0.0) are seeded BEFORE the
    concurrent claim batch runs.

    The sweep touches only rows with status='ready' AND readiness_score==0.0,
    making it cheap to run every iteration so mid-run promotions are seeded
    on the next tick.

    Parameters
    ----------
    project_id:
        UUID of the project whose ready features should be seeded.

    Returns
    -------
    int
        Number of features whose readiness_score was updated (0 if all
        ready features already had a non-zero readiness_score).
    """
    from bob3.run_loop import readiness_seed_sweep

    return readiness_seed_sweep(project_id)
