"""Feature-level utility functions for bob.

This module provides feature-level operations including the canonical
readiness derivation function.

Satisfies AC: 'Function defined: bob.feature.readiness_score_derived'
"""

from __future__ import annotations

__all__ = ["readiness_score_derived"]


def readiness_score_derived(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Derive readiness live from current confidence components.

    readiness_score MUST be DERIVED, not STORED-AND-DECAYED. Every read of
    readiness_score MUST be the live recomputation:
        mean(conf_impl_correctness, conf_spec_understanding, conf_test_quality)

    Confidence components themselves may decay (those are signal); readiness
    aggregates them at read time. _decay_confidence_after_failure decays
    components ONLY; it must not write readiness_score.

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
    from bob.readiness import derive_readiness_score

    return derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )
