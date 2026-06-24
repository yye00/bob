"""Live confidence assessment for bob74 features.

assess_feature_confidence derives readiness from the feature's DEMONSTRATED
spec_quality_score (earned at the ready-promotion gate), NOT from the
conservative AC-count heuristic that capped readiness at 0.56.

Required mapping (per feature description):
  standalone: readiness = spec_quality_score * 0.92
  integration: readiness = spec_quality_score * 0.30
  fallback (no composite): readiness = min(spec, impl, test)

This severs the chicken-and-egg deadlock where features at readiness=0.0
could never be claimed (claim gate requires readiness >= threshold), never
get assessed, and stay 0.0 forever.
"""

from __future__ import annotations

from bob.confidence import assess_feature_confidence

__all__ = ["assess_feature_confidence"]
