"""Stuck-readiness decomposition trigger — kill the eval-demotion treadmill.

If a feature has refinement_attempts >= 2 AND readiness_score < 0.80 AND no
readiness improvement this attempt, mark it ``pending_decomposition`` instead of
re-executing. Decomposition produces sub-features; the parent re-enters ``ready``
only once each sub-feature passes its own gate.

Exposed API
-----------
check_stuck_readiness(feature, *, previous_readiness_score=None) -> bool
    Return True when the feature is stuck and should be decomposed.

mark_pending_decomposition(feature, *, db_update=None) -> Feature
    Mark the feature status as ``pending_decomposition`` and optionally persist it.

Integration: bob3.orchestrator calls ``check_stuck_readiness`` before re-queuing a
feature and ``mark_pending_decomposition`` when the trigger fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bob3.models import Feature

_DECOMPOSE_READINESS_THRESHOLD = 0.80
_DECOMPOSE_MIN_ATTEMPTS = 2


def check_stuck_readiness(
    feature: "Feature",
    *,
    previous_readiness_score: float | None = None,
) -> bool:
    """Return True when the feature is stuck and should be decomposed.

    All three conditions must hold:
      1. refinement_attempts >= 2
      2. readiness_score < 0.80
      3. readiness did not improve since last attempt (or no prior score exists)

    Raises ValueError if feature.refinement_attempts is negative (data corruption).
    """
    if feature.refinement_attempts < 0:
        raise ValueError(
            f"feature.refinement_attempts is negative "
            f"({feature.refinement_attempts}) for feature {feature.id!r}; "
            "this indicates data corruption"
        )

    if feature.refinement_attempts < _DECOMPOSE_MIN_ATTEMPTS:
        return False

    if feature.readiness_score >= _DECOMPOSE_READINESS_THRESHOLD:
        return False

    return _no_readiness_improvement(feature.readiness_score, previous_readiness_score)


def mark_pending_decomposition(
    feature: "Feature",
    *,
    db_update: Any | None = None,
) -> "Feature":
    """Mark a stuck feature as pending_decomposition.

    Sets the feature status to ``pending_decomposition`` so a decomposer can
    split it into smaller sub-features. When ``db_update`` is provided it is
    called as ``db_update(feature.id, status="pending_decomposition")`` to
    persist the transition.

    Returns a copy of the feature with status set to ``pending_decomposition``.

    Raises ValueError if feature.refinement_attempts is negative.
    """
    if feature.refinement_attempts < 0:
        raise ValueError(
            f"feature.refinement_attempts is negative "
            f"({feature.refinement_attempts}) for feature {feature.id!r}; "
            "this indicates data corruption"
        )

    updated = feature.model_copy(update={"status": "pending_decomposition"})

    if db_update is not None:
        db_update(feature.id, status="pending_decomposition")

    return updated


def _no_readiness_improvement(current_score: float, previous_score: float | None) -> bool:
    """Return True when current_score did not improve over previous_score.

    None previous_score is treated conservatively as no improvement.
    """
    if previous_score is None:
        return True
    return current_score <= previous_score
