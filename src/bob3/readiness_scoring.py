"""Readiness scoring facade for bob3 (feature c13e7eb9).

readiness_score MUST be derived from current confidence components on each
read — never stored as decaying state that ratchets a feature toward terminal
demotion regardless of fresh signal.

This module is the canonical entry point for:
  AC: 'File exists: src/bob3/readiness_scoring.py'
  AC: 'Function defined: bob3.readiness_scoring.derive_readiness_from_components'
  AC: 'Function defined: bob3.readiness_scoring.seed_zero_readiness_features'

Design invariant:
    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves may decay (they are the signal); readiness
aggregates them at read time. ``_decay_confidence_after_failure`` MUST decay
components ONLY — it MUST NOT write ``readiness_score``.
"""

from __future__ import annotations

import math

from bob3.readiness import derive_readiness_score as _derive_readiness_score
from bob3.run_loop import seed_readiness_at_iteration_start as _seed_readiness_at_iteration_start

__all__ = [
    "derive_readiness_from_components",
    "seed_zero_readiness_features",
]


def derive_readiness_from_components(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Derive readiness live from current confidence components.

    Satisfies AC: 'Function defined: bob3.readiness_scoring.derive_readiness_from_components'.

    Computes ``mean(impl, spec, test)`` from the live confidence values,
    intentionally bypassing the persisted ``readiness_score`` column which may
    hold a stale decayed value from a prior run_loop failure ratchet.

    The caller MUST supply the live component values read directly from the
    feature row (not cached or decayed intermediates).

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


def seed_zero_readiness_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Satisfies AC: 'Function defined: bob3.readiness_scoring.seed_zero_readiness_features'.

    Must be called at the TOP of each orchestrator iteration, BEFORE the
    concurrent claim batch runs. This breaks the chicken-and-egg deadlock:

    - ``features_ready`` view requires ``readiness_score >= threshold``
    - ``assess_feature_confidence`` is only called AFTER a feature is claimed
    - Fresh features at 0.0 can never be claimed, never get assessed, stay 0.0

    The sweep touches only rows with ``status='ready' AND readiness_score==0.0``,
    making it cheap to run every iteration so mid-run promotions (features that
    just cleared the spec_quality gate this tick) are seeded on the next tick.

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
