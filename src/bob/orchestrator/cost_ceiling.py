"""Per-feature cost ceiling for the orchestrator.

AC: File exists: src/bob/orchestrator/cost_ceiling.py
AC: Function defined: bob.orchestrator.cost_ceiling.compute_per_feature_ceiling

The empirical p95 of real per-feature costs observed in bob v.16/17 runs
is ~$20. That is the default; operators can override via the environment
variable ``BOB_PER_FEATURE_COST_CEILING``.
"""

from __future__ import annotations

from bob.orchestrator.per_feature_ceiling import compute_per_feature_ceiling  # noqa: F401

__all__ = ["compute_per_feature_ceiling"]
