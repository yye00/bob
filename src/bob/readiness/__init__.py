"""Readiness assessment and derivation logic for bob.

readiness_score MUST be derived from current confidence components on each
read — never stored as decaying state. This prevents the monotonic ratchet
where successive failures push a recoverable feature into needs_human
regardless of fresh signal.

Design invariant:
    readiness_score = mean(conf_impl_correctness,
                           conf_spec_understanding,
                           conf_test_quality)

Confidence components themselves decay (they are signal); readiness
aggregates them at read time.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def check_bootstrap_override(feature) -> bool:
    """Return True if the feature may bypass the readiness gate exactly once.

    A feature is eligible for a bootstrap override when:
      - bootstrap_attempts < 1  (the single bypass has not been consumed)
      - research_iterations == 0  (no research signal exists yet)

    This resolves the self-referential deadlock where a feature cannot gain
    execution signal (needed to raise readiness) because the readiness gate
    blocks execution.

    Args:
        feature: A Feature instance with bootstrap_attempts and research_iterations.

    Returns:
        True if one bypass execution should be allowed; False otherwise.

    Raises:
        ValueError: If bootstrap_attempts or research_iterations is negative.
    """
    bootstrap_attempts = feature.bootstrap_attempts if feature.bootstrap_attempts is not None else 0
    research_iterations = feature.research_iterations if feature.research_iterations is not None else 0

    if bootstrap_attempts < 0:
        raise ValueError(
            f"bootstrap_attempts must be non-negative, got {bootstrap_attempts}"
        )
    if research_iterations < 0:
        raise ValueError(
            f"research_iterations must be non-negative, got {research_iterations}"
        )

    return bool(bootstrap_attempts < 1 and research_iterations == 0)


def _validate_component(name: str, value: object) -> float:
    """Validate a confidence component and return it as float.

    Raises ValueError for booleans, non-numeric types, non-finite values,
    or values outside [0.0, 1.0].
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"{name} must be a float in [0.0, 1.0], got {type(value).__name__}: {value!r}"
        )
    fval = float(value)
    if not math.isfinite(fval):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if fval < 0.0 or fval > 1.0:
        raise ValueError(f"{name} must be in [0.0, 1.0], got {value!r}")
    return fval


def derive_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Return readiness derived live from current confidence components.

    Computes mean(impl, spec, test). The persisted readiness_score column
    is intentionally ignored; callers must pass the live component values.

    Parameters map to the feature model columns:
        conf_impl_correctness  → Feature.conf_impl_correctness
        conf_spec_understanding → Feature.conf_spec_understanding
        conf_test_quality       → Feature.conf_test_adequacy (alias)

    Raises
    ------
    ValueError
        If any component is not a finite float in [0.0, 1.0].
    """
    impl = _validate_component("conf_impl_correctness", conf_impl_correctness)
    spec = _validate_component("conf_spec_understanding", conf_spec_understanding)
    test = _validate_component("conf_test_quality", conf_test_quality)
    return (impl + spec + test) / 3.0


def rederive_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
    previous_readiness_score: float | None = None,
) -> float:
    """Recompute readiness live from the CURRENT confidence components.

    This is the anti-ratchet entry point. On every refinement attempt the
    readiness_score MUST be *rederived* from the feature's current confidence
    components — it is never carried forward as a stored, decaying value. That
    prevents the monotonic ``0.85→0.70→0.55→0.40`` slide that silently steered
    every flaky-but-recoverable feature into ``needs_human``.

    The confidence components themselves may decay (they are signal);
    ``readiness_score`` merely aggregates them at read time as their mean.

    Parameters
    ----------
    conf_impl_correctness, conf_spec_understanding, conf_test_quality:
        The feature's live confidence components in ``[0.0, 1.0]``.
    previous_readiness_score:
        The stale, possibly-decayed prior readiness value. It is accepted for
        call-site symmetry and validated, but is INTENTIONALLY IGNORED in the
        computation — a decayed prior must never drag down a fresh recompute.

    Returns
    -------
    float
        ``mean(conf_impl_correctness, conf_spec_understanding, conf_test_quality)``.

    Raises
    ------
    ValueError
        If any component (or ``previous_readiness_score`` when supplied) is not
        a finite float in ``[0.0, 1.0]``.
    """
    if previous_readiness_score is not None:
        _validate_component("previous_readiness_score", previous_readiness_score)

    return derive_readiness_score(
        conf_impl_correctness=conf_impl_correctness,
        conf_spec_understanding=conf_spec_understanding,
        conf_test_quality=conf_test_quality,
    )


def assess_feature_confidence(feature_id: str) -> dict[str, float]:
    """Assess a feature's confidence components and derive its readiness.

    Package-level entry point satisfying AC
    'Function defined: bob.readiness.assess_feature_confidence'. Delegates to
    the canonical :func:`bob.db.assess_feature_confidence`, which derives
    readiness from the demonstrated ``spec_quality_score`` composite (falling
    back to the AC-count heuristic only when no composite exists yet).

    Parameters
    ----------
    feature_id:
        UUID of the feature to assess.

    Returns
    -------
    dict[str, float]
        Keys: ``conf_spec_understanding``, ``conf_impl_correctness``,
        ``conf_test_adequacy``, ``readiness_score``. A missing feature yields
        an all-zero dict rather than raising.
    """
    from bob.db import assess_feature_confidence as _db_assess

    return _db_assess(feature_id)


def compute_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Derive readiness live from current confidence components.

    Public entry point satisfying AC 'Function defined: bob.readiness.compute_readiness_score'.
    Delegates to derive_readiness_score — see that function for validation rules and
    invariant documentation.

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


def compute_readiness_live(feature_id: str) -> float | None:
    """Derive readiness from the feature's current confidence components in the DB.

    Public entry point satisfying AC 'Function defined: bob.readiness.compute_readiness_live'.
    Reads conf_impl_correctness, conf_spec_understanding, conf_test_adequacy
    from the feature row and returns mean(impl, spec, test).

    The persisted readiness_score column is intentionally bypassed — it may
    hold a stale decayed value from a prior run_loop failure ratchet.

    Returns None if the feature does not exist.
    """
    return calculate_readiness_live(feature_id)


def calculate_readiness_live(feature_id: str) -> float | None:
    """Derive readiness from the feature's current confidence components in the DB.

    Reads conf_impl_correctness, conf_spec_understanding, conf_test_adequacy
    from the feature row and returns mean(impl, spec, test).

    The persisted readiness_score column is intentionally bypassed — it may
    hold a stale decayed value from a prior run_loop failure ratchet.

    Returns None if the feature does not exist.
    """
    from bob.db import get_feature

    feature = get_feature(feature_id)
    if feature is None:
        return None

    impl = float(feature.conf_impl_correctness or 0.0)
    spec = float(feature.conf_spec_understanding or 0.0)
    test = float(feature.conf_test_adequacy or 0.0)

    return (impl + spec + test) / 3.0


def restore_baseline_confidence(feature_id: str) -> bool:
    """Restore a feature's confidence components to their baseline (creation-time) values.

    The RCA auto-reset path (F-R7-479) bounces a feature back to 'ready' and
    resets refinement_attempts but does NOT restore the confidence components that
    have been decayed by _decay_confidence_after_failure.  This function fills that
    gap: it re-derives readiness from the feature's spec_quality_score (if present)
    or from the AC-count heuristic, then persists the result so the next claim sweep
    sees a valid readiness value rather than the decayed floor.

    Parameters
    ----------
    feature_id:
        UUID of the feature to restore.

    Returns
    -------
    bool
        True if the feature was found and updated; False if the feature does not exist.
    """
    from bob.db import assess_feature_confidence, get_feature, update_feature

    feature = get_feature(feature_id)
    if feature is None:
        return False

    assessment = assess_feature_confidence(feature_id)

    update_feature(
        feature_id,
        conf_impl_correctness=assessment.get("conf_impl_correctness", 0.0),
        conf_spec_understanding=assessment.get("conf_spec_understanding", 0.0),
        conf_test_adequacy=assessment.get("conf_test_adequacy", 0.0),
        readiness_score=assessment.get("readiness_score", 0.0),
    )
    return True


def check_pending_decomposition(
    feature: object,
    *,
    previous_readiness_score: float | None = None,
) -> bool:
    """Return True when the feature is stuck and should be decomposed.

    Satisfies AC: 'Function defined: bob.readiness.check_pending_decomposition'

    Delegates to bob.stuck_readiness_decomposer.check_stuck_readiness which
    enforces all three conditions:
      1. refinement_attempts >= 2
      2. readiness_score < 0.80
      3. readiness did not improve since last attempt (or no prior score)

    Raises ValueError if feature.refinement_attempts is negative.
    """
    from bob.stuck_readiness_decomposer import check_stuck_readiness

    return check_stuck_readiness(feature, previous_readiness_score=previous_readiness_score)


def seed_zero_readiness_features(project_id: str) -> int:
    """Seed readiness for all ready features with readiness_score == 0.0 in a project.

    This is the AC-satisfying entry point for
    'Function defined: bob.readiness.seed_zero_readiness_features'.

    For every feature with status='ready' AND readiness_score==0.0, calls
    assess_feature_confidence and persists the derived readiness so the next
    claim batch can fill its 8-wide concurrency slot.

    The sweep is cheap: it only touches rows where readiness_score==0.0, so it
    can run at the top of every run_loop iteration without meaningful overhead.

    Parameters
    ----------
    project_id:
        The project to sweep. Only features belonging to this project are touched.

    Returns
    -------
    int
        Number of features that were seeded (had their readiness updated).
    """
    from bob.db import assess_feature_confidence, get_features_by_project, update_feature

    seeded = 0
    features = get_features_by_project(project_id)
    for feature in features:
        if feature.status != "ready":
            continue
        if feature.readiness_score is not None and feature.readiness_score != 0.0:
            continue

        fid = feature.id
        assessment = assess_feature_confidence(fid)
        new_readiness = assessment.get("readiness_score", 0.0)
        if new_readiness and new_readiness > 0.0:
            update_feature(
                fid,
                conf_impl_correctness=assessment.get("conf_impl_correctness", 0.0),
                conf_spec_understanding=assessment.get("conf_spec_understanding", 0.0),
                conf_test_adequacy=assessment.get("conf_test_adequacy", 0.0),
                readiness_score=new_readiness,
            )
            seeded += 1

    return seeded


def seed_readiness_for_ready_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature with readiness_score == 0.0.

    Alias for :func:`seed_zero_readiness_features` satisfying AC
    'Function defined: bob.readiness.seed_readiness_for_ready_features'.

    Sweeps features with ``status='ready' AND readiness_score==0.0`` in the given
    project, derives readiness from the demonstrated spec_quality_score (or AC-count
    heuristic fallback), and persists the result.  Must be called at the top of each
    run_loop iteration to break the chicken-and-egg deadlock where fresh features at
    0.0 can never be claimed by the gated ``find_next_ready_feature`` query.

    Parameters
    ----------
    project_id:
        UUID of the project whose ready features should be seeded.

    Returns
    -------
    int
        Number of features whose ``readiness_score`` was updated (> 0.0 after seeding).
    """
    return seed_zero_readiness_features(project_id)
