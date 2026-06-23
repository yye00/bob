"""Run loop utilities for bob75.

Exposes seed_readiness_at_iteration_start, which seeds readiness_score for
every ready feature that still sits at 0.0.

The run loop MUST call this sweep at the TOP OF EACH ITERATION — before the
concurrent claim batch runs — to seed all freshly-promoted features together
so the 8-wide batch can fill. This fixes the second half of the chicken-and-egg
deadlock: even after assess_feature_confidence is fixed to derive from
spec_quality_score rather than the AC-count heuristic, it is only called for
already-claimed features. Fresh ready features at 0.0 are never selected, never
assessed, and stay at 0.0. The sweep corrects this by proactively seeding all
zero-readiness ready features before the claim batch runs.
"""

from __future__ import annotations

from bob3.run_loop import seed_readiness_at_iteration_start

__all__ = ["seed_readiness_at_iteration_start"]
