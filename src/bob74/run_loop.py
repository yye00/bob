"""Run loop utilities for bob74.

Exposes seed_readiness_for_zero_features, which seeds readiness_score for
every ready feature that still sits at 0.0.

The run loop MUST call this sweep at the TOP OF EACH ITERATION — before the
concurrent claim batch runs — to seed all freshly-promoted features together
so the 8-wide batch can actually fill.
"""

from __future__ import annotations

from bob3.run_loop import seed_readiness_at_iteration_start

__all__ = ["seed_readiness_for_zero_features"]


def seed_readiness_for_zero_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Delegates to bob3.run_loop.seed_readiness_at_iteration_start — see that
    function for full documentation.

    This is the canonical entry point for the AC:
      'Function defined: bob74.run_loop.seed_readiness_for_zero_features'

    Parameters
    ----------
    project_id:
        The project whose ready-but-unscored features should be seeded.

    Returns
    -------
    int
        Number of features whose readiness_score was updated (0 if all
        non-zero readiness_score or no ready features exist).
    """
    return seed_readiness_at_iteration_start(project_id)
