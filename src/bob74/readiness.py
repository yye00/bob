"""Live readiness derivation for bob74 features.

readiness_score MUST be derived from current confidence components on each
read — never stored as decaying state. This prevents the monotonic ratchet
where successive failures push a recoverable feature into needs_human
regardless of fresh signal.

Design invariant:
    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves decay (they are signal); readiness
aggregates them at read time.
"""

from __future__ import annotations

from bob3.readiness import calculate_readiness_live, derive_readiness_score

__all__ = ["calculate_readiness_live", "derive_readiness_score"]
