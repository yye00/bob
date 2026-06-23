"""Live readiness derivation for bob3 features.

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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def calculate_readiness_live(feature_id: str) -> float | None:
    """Derive readiness from the feature's current confidence components in the DB.

    Reads conf_impl_correctness, conf_spec_understanding, conf_test_adequacy
    from the feature row and returns mean(impl, spec, test).

    The persisted readiness_score column is intentionally bypassed — it may
    hold a stale decayed value from a prior run_loop failure ratchet.

    Returns None if the feature does not exist.
    """
    from bob3.db import get_feature

    feature = get_feature(feature_id)
    if feature is None:
        return None

    impl = float(feature.conf_impl_correctness or 0.0)
    spec = float(feature.conf_spec_understanding or 0.0)
    test = float(feature.conf_test_adequacy or 0.0)

    return (impl + spec + test) / 3.0


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
    import math

    components = {
        "conf_impl_correctness": conf_impl_correctness,
        "conf_spec_understanding": conf_spec_understanding,
        "conf_test_quality": conf_test_quality,
    }
    for name, value in components.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"{name} must be a float in [0.0, 1.0], got {type(value).__name__}: {value!r}"
            )
        if not math.isfinite(value):
            raise ValueError(
                f"{name} must be finite, got {value!r}"
            )
        if value < 0.0 or value > 1.0:
            raise ValueError(
                f"{name} must be in [0.0, 1.0], got {value!r}"
            )

    return (conf_impl_correctness + conf_spec_understanding + conf_test_quality) / 3.0


def compute_readiness_score(
    *,
    conf_impl_correctness: float,
    conf_spec_understanding: float,
    conf_test_quality: float,
) -> float:
    """Derive readiness live from current confidence components.

    Public entry point satisfying AC 'Function defined: bob3.readiness.compute_readiness_score'.
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
    from bob3.db import assess_feature_confidence, get_feature, update_feature

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
