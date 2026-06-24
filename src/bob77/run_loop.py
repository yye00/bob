"""Run loop utilities for bob77.

Exposes seed_readiness_for_zero_score_features, which seeds readiness_score for
every ready feature that still sits at 0.0.

The run loop MUST call this sweep at the TOP OF EACH ITERATION — before the
concurrent claim batch runs — to seed all freshly-promoted features together
so the 8-wide batch can actually fill.

This fixes the second half of the chicken-and-egg deadlock:
  - features_ready view requires readiness_score >= threshold
  - assess_feature_confidence is only invoked AFTER a feature is claimed
  - → fresh features at 0.0 can never be claimed, never assessed, stay 0.0

The sweep touches only rows with status='ready' AND readiness_score==0.0,
making it cheap regardless of total feature count.
"""

from __future__ import annotations

from bob.run_loop import seed_readiness_at_iteration_start

__all__ = ["seed_readiness_for_zero_score_features"]


def seed_readiness_for_zero_score_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Delegates to bob.run_loop.seed_readiness_at_iteration_start — see that
    function for full documentation.

    This is the canonical bob77 entry point for the AC:
      'Function defined: bob77.run_loop.seed_readiness_for_zero_score_features'

    The run loop MUST call this at the TOP OF EACH ITERATION, before the
    concurrent claim batch, so all freshly-promoted features are seeded
    together and the 8-wide concurrency batch can fill.

    Parameters
    ----------
    project_id:
        The project whose ready-but-unscored features should be seeded.

    Returns
    -------
    int
        Number of features whose readiness_score was updated (0 if all
        already have non-zero readiness_score or no ready features exist).
    """
    return seed_readiness_at_iteration_start(project_id)
