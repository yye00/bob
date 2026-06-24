"""Readiness derivation utilities for bob77.

Exposes derive_readiness_from_components, the bob77 entry point for live
readiness derivation from current confidence components.

Design invariant:
    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

readiness_score is DERIVED, not stored-and-decayed. Confidence components
themselves may decay (they are signal); readiness aggregates them at read time.
_decay_confidence_after_failure decays components ONLY — it MUST NOT write
readiness_score.

This severs the monotonic ratchet (0.85 → 0.70 → 0.55 → 0.40 across failures)
that previously steered every flaky-but-recoverable feature into terminal
needs_human state.
"""

from __future__ import annotations

from bob3.readiness import derive_readiness_score

__all__ = ["derive_readiness_from_components"]


def derive_readiness_from_components(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Computes mean(impl, spec, test). The persisted readiness_score column
    is intentionally ignored; callers must pass the live component values.

    This is the canonical bob77 entry point for the readiness rederivation
    fix (feature 15ba2adc). It delegates to bob3.readiness.derive_readiness_score.

    Parameters
    ----------
    conf_impl_correctness:
        Current value of Feature.conf_impl_correctness (0.0–1.0).
    conf_spec_understanding:
        Current value of Feature.conf_spec_understanding (0.0–1.0).
    conf_test_quality:
        Current value of Feature.conf_test_adequacy (0.0–1.0).

    Returns
    -------
    float
        Derived readiness in [0.0, 1.0].

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    return derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )
