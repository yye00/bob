"""Per-feature cost ceiling for the orchestrator.

AC: File exists: src/bob3/orchestrator/cost_ceiling.py
AC: Function defined: bob3.orchestrator.cost_ceiling.compute_per_feature_ceiling

The empirical p95 of real per-feature costs observed in bob3 v.16/17 runs
is ~$20. That is the default; operators can override via the environment
variable ``BOB3_PER_FEATURE_COST_CEILING``.
"""

from __future__ import annotations

from bob3.orchestrator.per_feature_ceiling import compute_per_feature_ceiling  # noqa: F401

__all__ = ["compute_per_feature_ceiling"]
