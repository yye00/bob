"""Readiness score derivation — live from confidence components.

readiness_score MUST be rederived from current confidence components on each
refinement attempt, not stored as decaying state that ratchets a feature toward
terminal demotion regardless of fresh signal.

Design invariant::

    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves may decay (they are the signal); readiness
aggregates them at read time. ``_decay_confidence_after_failure`` MUST decay
components ONLY — it MUST NOT write ``readiness_score``.

This module is the canonical AC-satisfying entry point for feature
7042c0c5-4666-413f-93ca-42fc4d8fc169.
"""

from __future__ import annotations

from bob3.readiness import derive_readiness_score as _derive_readiness_score

__all__ = [
    "compute_readiness_from_components",
    "derive_readiness_from_confidence",
    "derive_readiness_score",
    "seed_zero_readiness_features",
]


def compute_readiness_from_components(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Satisfies AC: 'Function defined: bob3.readiness_score.compute_readiness_from_components'.

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

    Satisfies AC: 'Function defined: bob3.readiness_score.seed_zero_readiness_features'.

    Breaks the chicken-and-egg deadlock: ``features_ready`` view requires
    ``readiness_score >= threshold``, but ``assess_feature_confidence`` is only
    called after a feature is claimed. Fresh features at 0.0 can never be
    claimed, never get assessed, and stay 0.0 forever.

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
    from bob3.readiness_derivation import seed_zero_readiness_features as _seed

    return _seed(project_id)


def derive_readiness_from_confidence(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Satisfies AC: 'Function defined: bob3.readiness_score.derive_readiness_from_confidence'.

    Computes ``mean(impl, spec, test)`` from the live confidence values.
    The persisted ``readiness_score`` column is intentionally bypassed; callers
    must supply the live component values read directly from the feature row.

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


def derive_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Alias for derive_readiness_from_confidence.

    Provided for callers that prefer the ``derive_readiness_score`` name.

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
