"""bob.decomposition — stuck-readiness decomposition trigger.

Exposes three public functions used by the orchestrator to detect when a
feature is stuck in the eval-demotion treadmill and decompose it into
smaller sub-features.

Public API
----------
should_trigger_decomposition(feature, *, previous_readiness_score=None) -> bool
    Return True when refinement_attempts >= 2, readiness_score < 0.80, and
    readiness did not improve since the last attempt.

mark_pending_decomposition(feature, *, db_update=None) -> Feature
    Set feature.status to "pending_decomposition" and optionally persist.

create_sub_features(parent_feature, children_specs, *, project_id) -> list[Feature]
    Create child Feature rows from a list of spec dicts under parent_feature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bob.models import Feature

_DECOMPOSE_READINESS_THRESHOLD = 0.80
_DECOMPOSE_MIN_ATTEMPTS = 2


def should_trigger_decomposition(
    feature: "Feature",
    *,
    previous_readiness_score: float | None = None,
) -> bool:
    """Return True when decomposition should replace re-execution.

    All three conditions must hold:
      1. refinement_attempts >= 2
      2. readiness_score < 0.80
      3. readiness did not improve since last attempt (or no prior score)

    Raises ValueError if feature.refinement_attempts is negative (data
    corruption guard — error message contains "negative" and feature.id).
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

    Sets the feature status to "pending_decomposition". When ``db_update``
    is provided it is called as
    ``db_update(feature.id, status="pending_decomposition")`` to persist
    the transition.

    Returns a copy of the feature with status set to "pending_decomposition".

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


def create_sub_features(
    parent_feature: "Feature",
    children_specs: list[dict],
    *,
    project_id: str,
) -> list["Feature"]:
    """Create child Feature rows from a list of spec dicts.

    Each element of ``children_specs`` is a dict with optional keys:
      - name (str): child feature name; defaults to "Child of <parent>"
      - description (str): child description
      - acceptance_criteria (str): child ACs
      - priority (int): child priority; defaults to parent's priority
      - risk_category (str): child risk; defaults to parent's risk_category

    Uses ``bob.db.create_child_feature`` to persist each child. Raises
    ValueError if ``children_specs`` is empty, if any spec is not a dict,
    or if the db layer rejects the creation (e.g. max depth exceeded).

    Returns the list of created Feature objects in the same order as
    ``children_specs``.
    """
    if not children_specs:
        raise ValueError(
            "children_specs must not be empty; "
            "provide at least one child spec to decompose into"
        )

    from bob.db import create_child_feature  # deferred to avoid circular import

    created: list[Feature] = []
    for idx, spec in enumerate(children_specs):
        if not isinstance(spec, dict):
            raise ValueError(
                f"children_specs[{idx}] must be a dict, got {type(spec).__name__!r}"
            )
        child = create_child_feature(
            parent_feature_id=parent_feature.id,
            project_id=project_id,
            name=spec.get("name") or f"Child of {parent_feature.name}",
            description=spec.get("description"),
            acceptance_criteria=spec.get("acceptance_criteria"),
            status="ready",
            priority=spec.get("priority", parent_feature.priority),
            risk_category=spec.get("risk_category", getattr(parent_feature, "risk_category", "medium")),
        )
        created.append(child)

    return created


def spawn_sub_features(
    parent_feature: "Feature",
    children_specs: list[dict],
    *,
    project_id: str,
) -> list["Feature"]:
    """Spawn sub-features from a stuck parent feature.

    Satisfies AC: 'Function defined: bob.decomposition.spawn_sub_features'

    Delegates to create_sub_features — same contract, different public name
    aligning with the 'spawn' vocabulary used by the decomposition trigger spec.

    Each element of ``children_specs`` is a dict with optional keys:
      - name (str): child feature name; defaults to "Child of <parent>"
      - description (str): child description
      - acceptance_criteria (str): child ACs
      - priority (int): child priority; defaults to parent's priority
      - risk_category (str): child risk; defaults to parent's risk_category

    Raises ValueError if ``children_specs`` is empty or any spec is not a dict.
    Returns the list of created Feature objects in the same order as ``children_specs``.
    """
    return create_sub_features(parent_feature, children_specs, project_id=project_id)


def _no_readiness_improvement(current_score: float, previous_score: float | None) -> bool:
    """Return True when current_score did not improve over previous_score.

    None previous_score is treated conservatively as no improvement.
    """
    if previous_score is None:
        return True
    return current_score <= previous_score
