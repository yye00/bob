"""Top-level re-export shim for bob3.orchestrator.cost_projection.

Exposes the cost-projection gate functions at the shorter ``bob3.cost_projection``
path so callers and acceptance-criterion verifiers can reference the module without
knowing its orchestrator-package location.
"""

from bob3.orchestrator.cost_projection import (  # noqa: F401
    allow_spawn,
    project_feature_cost,
    DEFAULT_FALLBACK_ESTIMATE_USD,
    MIN_SAMPLES_FOR_BUCKET_ESTIMATE,
)

__all__ = [
    "allow_spawn",
    "project_feature_cost",
    "DEFAULT_FALLBACK_ESTIMATE_USD",
    "MIN_SAMPLES_FOR_BUCKET_ESTIMATE",
]
