"""Stuck-readiness decomposition trigger — kill the eval-demotion treadmill.

When a feature has been attempted >= 2 times with readiness_score < 0.80 and no
improvement since the last attempt, continuing to re-execute is a treadmill: the
eval sub-agent demotes confidence, charges refinement_attempts, and leaves the
feature stuck. This module detects that condition and marks the feature
``pending_decomposition`` so a decomposer can split it into smaller sub-features.

The three conditions that must ALL be true:
    1. refinement_attempts >= 2
    2. readiness_score < 0.80
    3. no readiness improvement since last attempt

The parent feature re-enters ``ready`` only once each sub-feature passes its own gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob3.models import Feature

_DECOMPOSE_READINESS_THRESHOLD = 0.80
_DECOMPOSE_MIN_ATTEMPTS = 2


def stuck_readiness_decomposition_trigger_kill_eval_demotion_treadmill(
    feature: "Feature",
    *,
    previous_readiness_score: float | None = None,
) -> str:
    """Evaluate a feature and return the next orchestration action.

    Returns ``"decompose"`` when all three conditions are met:
      - refinement_attempts >= 2
      - readiness_score < 0.80
      - readiness did not improve since last attempt (or no prior score available)

    Returns ``"execute"`` otherwise.

    Raises ValueError if feature.refinement_attempts is negative (data corruption).
    """
    if feature.refinement_attempts < 0:
        raise ValueError(
            f"feature.refinement_attempts is negative "
            f"({feature.refinement_attempts}) for feature {feature.id!r}; "
            "this indicates data corruption"
        )

    if feature.refinement_attempts < _DECOMPOSE_MIN_ATTEMPTS:
        return "execute"

    if feature.readiness_score >= _DECOMPOSE_READINESS_THRESHOLD:
        return "execute"

    if not _no_improvement(feature.readiness_score, previous_readiness_score):
        return "execute"

    return "decompose"


def _no_improvement(current_score: float, previous_score: float | None) -> bool:
    """Return True when current_score did not improve over previous_score.

    A None previous_score is treated conservatively as no improvement.
    """
    if previous_score is None:
        return True
    return current_score <= previous_score
