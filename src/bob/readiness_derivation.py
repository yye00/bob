"""Readiness derivation facade for bob.

readiness_score MUST be rederived from current confidence components on each
refinement attempt — not stored as decaying state that ratchets a feature toward
terminal demotion regardless of fresh signal.

This module is the canonical entry point for feature 3205cc9d-50db-471f-b673-14046d3d158e.
It exposes:

1. :func:`derive_readiness_score` — derives readiness live from confidence components,
   bypassing the stale persisted ``readiness_score`` column.

2. :func:`seed_zero_readiness_features` — sweeps all ready features with
   ``readiness_score == 0.0`` and seeds them from their demonstrated
   ``spec_quality_score``, breaking the chicken-and-egg deadlock where fresh
   features at 0.0 can never be claimed.

Design invariant::

    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves may decay (they are the signal); readiness
aggregates them at read time.  ``_decay_confidence_after_failure`` MUST decay
components ONLY — it MUST NOT write ``readiness_score``.
"""

from __future__ import annotations

from bob.readiness import derive_readiness_score as _derive_readiness_score
from bob.run_loop import seed_readiness_at_iteration_start as _seed_readiness_at_iteration_start

__all__ = [
    "compute_readiness_score",
    "derive_readiness_score",
    "derive_readiness_from_confidence",
    "seed_zero_readiness_features",
]


def compute_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Satisfies AC: 'Function defined: bob.readiness_derivation.compute_readiness_score'.
    Delegates to derive_readiness_score — see that function for full documentation.

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    return _derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def derive_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Computes ``mean(impl, spec, test)`` from the live confidence values.
    The persisted ``readiness_score`` column is intentionally bypassed.

    Parameters
    ----------
    conf_impl_correctness:
        Current value of ``Feature.conf_impl_correctness`` (0.0–1.0).
    conf_spec_understanding:
        Current value of ``Feature.conf_spec_understanding`` (0.0–1.0).
    conf_test_quality:
        Current value of ``Feature.conf_test_adequacy`` (0.0–1.0).

    Returns
    -------
    float
        Derived readiness in [0.0, 1.0].

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    return _derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def derive_readiness_from_confidence(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Alias for :func:`derive_readiness_score` satisfying AC
    'Function defined: bob.readiness_derivation.derive_readiness_from_confidence'.

    Computes ``mean(impl, spec, test)`` from the live confidence values.
    The persisted ``readiness_score`` column is intentionally bypassed.

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    return _derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def seed_zero_readiness_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    This breaks the chicken-and-egg deadlock:

    - ``features_ready`` view requires ``readiness_score >= threshold``
    - ``assess_feature_confidence`` is only called AFTER a feature is claimed
    - Fresh features at 0.0 can never be claimed, never assessed, stay 0.0 forever

    The sweep touches only rows with ``status='ready' AND readiness_score==0.0``,
    making it cheap to run at the top of every orchestrator iteration.

    Parameters
    ----------
    project_id:
        UUID of the project whose ready features should be seeded.

    Returns
    -------
    int
        Number of features whose ``readiness_score`` was updated.
    """
    return _seed_readiness_at_iteration_start(project_id)
