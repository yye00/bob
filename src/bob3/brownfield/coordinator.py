"""Brownfield coordinator — BF-4 Hierarchical Localizer integration.

AC: integration: bob3.brownfield.coordinator

Wires the BF-4 hierarchical localizer into the brownfield coordinator pipeline.
Provides coordinator-facing helpers for:

  1. Running localization before dispatching code-write subagents.
  2. Persisting localization results to feature.localization.
  3. Enforcing disjoint write surfaces across concurrently dispatched features.

Usage:
    from bob3.brownfield.coordinator import localize_feature, check_disjoint_features
"""

from __future__ import annotations

from bob3.brownfield.orchestrator import (
    check_disjoint_features,
    localize_feature,
    run_localization_pipeline,
)

__all__ = [
    "localize_feature",
    "check_disjoint_features",
    "run_localization_pipeline",
]
