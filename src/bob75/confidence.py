"""Confidence assessment utilities for bob75.

Exposes derive_readiness_score and assess_feature_confidence — the two
functions required to break the chicken-and-egg deadlock where features
with readiness_score==0.0 can never be claimed, never assessed, and stay
at 0.0 forever.

Design invariant:
    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves may decay (they are signal); readiness
aggregates them at read time and is NEVER stored as a decaying value.
"""

from __future__ import annotations

from bob.readiness import derive_readiness_score
from bob.db import assess_feature_confidence

__all__ = ["derive_readiness_score", "assess_feature_confidence"]
