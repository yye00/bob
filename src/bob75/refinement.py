"""bob75.refinement — Refinement-phase helpers for the orchestrator.

Provides :func:`check_stuck_readiness`, the gate that determines whether a
feature stuck in the refinement treadmill should be decomposed instead of
re-executed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob3.models import Feature

_DECOMPOSE_READINESS_THRESHOLD = 0.80
_DECOMPOSE_MIN_ATTEMPTS = 2


def check_stuck_readiness(
    feature: "Feature",
    *,
    previous_readiness_score: float | None = None,
) -> bool:
    """Return True when a feature is stuck and should be decomposed.

    All three conditions must hold:
      1. refinement_attempts >= 2
      2. readiness_score < 0.80
      3. readiness did not improve since last attempt (or no prior score exists)

    Raises ValueError if feature.refinement_attempts is negative.
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


def _no_readiness_improvement(current_score: float, previous_score: float | None) -> bool:
    if previous_score is None:
        return True
    return current_score <= previous_score
