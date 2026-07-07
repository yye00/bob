"""961667e0: readiness_score MUST be rederived from current confidence components.

Problem
-------
bob version 14 stored readiness_score as decaying state: every call to
``_decay_confidence_after_failure`` dropped readiness by 0.15, but the inverse
(recompute readiness from improved confidence components) never fired during
the refinement loop. ``db.calculate_readiness`` was only called at feature
CREATION. F-R7-479 RCA auto-reset bounced the feature back to ready but did
NOT restore the decayed readiness_score. Net effect: a feature that crashes
twice has readiness 0.85 → 0.70 → 0.55 → 0.40 monotonically, steering every
flaky-but-recoverable feature into terminal ``needs_human``.

Second half (bob59/bob62 investigation): ``assess_feature_confidence`` never
seeded readiness above 0.0 for a fresh feature, AND it was only invoked AFTER
a feature was claimed — which required readiness_score >= threshold. Fresh
features at 0.0 could never be claimed, never got assessed, stayed 0.0 forever.
This collapsed 8-wide concurrency to ~1.

Solution
--------
This module is the public facade for the readiness rederivation fix. It exposes:

1. :func:`readiness_score_must_rederived_current_confidence_components` — the
   canonical entry point that derives readiness live from confidence components
   instead of reading the stale persisted column.

2. Re-exports of :func:`~bob.readiness.derive_readiness_score` and
   :func:`~bob.run_loop.seed_readiness_at_iteration_start` for callers that
   need the lower-level primitives.

Design invariant:
    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves may decay (they are the signal); readiness
aggregates them at read time. ``_decay_confidence_after_failure`` MUST decay
components ONLY — it MUST NOT write readiness_score.
"""

from __future__ import annotations

import logging

from bob.readiness import derive_readiness_score, calculate_readiness_live
from bob.run_loop import seed_readiness_at_iteration_start

__all__ = [
    "readiness_score_must_rederived_current_confidence_components",
    "rederive_readiness_score",
    "seed_ready_features_readiness",
    "derive_readiness_score",
    "calculate_readiness_live",
    "seed_readiness_at_iteration_start",
]

logger = logging.getLogger(__name__)


def readiness_score_must_rederived_current_confidence_components(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    This is the canonical entry point for the readiness rederivation fix
    (feature 961667e0). It delegates to
    :func:`bob.readiness.derive_readiness_score`, which computes
    ``mean(impl, spec, test)`` from the live confidence values.

    The persisted ``readiness_score`` column is intentionally bypassed.
    The caller MUST supply the live component values read directly from
    the feature row (not cached or decayed intermediates).

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
        Derived readiness in [0.0, 1.0]. This value MUST be used in place
        of the stored ``readiness_score`` column whenever a gate decision
        (5-attempt cap, decomposition trigger, claim eligibility) depends
        on readiness.
    """
    return derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def rederive_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Rederive readiness live from current confidence components.

    Satisfies AC 'Function defined:
    bob.readiness_score_must_rederived_current_confidence_components.rederive_readiness_score'.

    Delegates to
    :func:`readiness_score_must_rederived_current_confidence_components`, which
    computes ``mean(impl, spec, test)`` from the live confidence values. The
    persisted ``readiness_score`` column is intentionally bypassed so a prior
    failure ratchet cannot suppress a recovered feature.

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    return readiness_score_must_rederived_current_confidence_components(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def seed_ready_features_readiness(project_id: str) -> int:
    """Seed ``readiness_score`` for every ready feature still sitting at 0.0.

    Satisfies AC 'Function defined:
    bob.readiness_score_must_rederived_current_confidence_components.seed_ready_features_readiness'.

    Runs at the TOP of each orchestrator iteration, BEFORE the concurrent claim
    batch, breaking the chicken-and-egg deadlock where a fresh feature at 0.0
    could never be claimed and therefore never assessed. Touches only rows with
    ``status='ready' AND readiness_score == 0.0``, so it is cheap to run every
    iteration.

    Delegates to :func:`bob.run_loop.seed_readiness_at_iteration_start`.

    Returns
    -------
    int
        Number of features whose ``readiness_score`` was updated.
    """
    return seed_readiness_at_iteration_start(project_id)
