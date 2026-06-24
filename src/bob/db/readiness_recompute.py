"""Live readiness recomputation — F-62a44904.

readiness_score is derived on read from the current confidence components,
never stored as decaying state. This prevents the monotonic ratchet where
successive failures push a recoverable feature into needs_human regardless
of fresh signal.

Design invariant: readiness_score = mean(conf_impl_correctness,
conf_spec_understanding, conf_test_adequacy). The persisted readiness_score
column is ignored; callers should use compute_live_readiness() instead.

Baseline storage: the creation-time confidence triple is stored under the
key "baseline_confidence" inside the readiness_components JSON column.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def compute_live_readiness(feature_id: str) -> float | None:
    """Return readiness derived from current confidence components.

    Reads conf_impl_correctness, conf_spec_understanding, conf_test_adequacy
    from the feature row and returns mean(impl, spec, test).

    The persisted readiness_score column is intentionally ignored; it may
    hold a stale decayed value from a previous run_loop iteration.

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


def snapshot_baseline_confidence(feature_id: str) -> None:
    """Store current confidence components as the baseline for this feature.

    Called at feature creation (or immediately after) so that
    restore_baseline_confidence can recover the original signal after an
    infra-caused decay.

    The triple (conf_impl_correctness, conf_spec_understanding,
    conf_test_adequacy) is serialised under the "baseline_confidence" key
    inside the readiness_components JSON column.

    Raises ValueError if the feature does not exist.
    """
    from bob.db import get_feature, update_feature

    feature = get_feature(feature_id)
    if feature is None:
        raise ValueError(f"Cannot snapshot baseline: feature {feature_id!r} not found")

    # Load existing readiness_components JSON (may be None or contain other keys)
    existing: dict = {}
    if feature.readiness_components:
        try:
            existing = json.loads(feature.readiness_components)
        except (json.JSONDecodeError, TypeError):
            existing = {}

    existing["baseline_confidence"] = {
        "conf_impl_correctness": float(feature.conf_impl_correctness or 0.0),
        "conf_spec_understanding": float(feature.conf_spec_understanding or 0.0),
        "conf_test_adequacy": float(feature.conf_test_adequacy or 0.0),
    }

    update_feature(feature_id, readiness_components=json.dumps(existing))
    logger.debug(
        "readiness_recompute: snapshotted baseline for feature %s: %s",
        feature_id[:8],
        existing["baseline_confidence"],
    )


def get_baseline_confidence(feature_id: str) -> dict | None:
    """Retrieve the stored baseline confidence triple.

    Returns a dict with keys conf_impl_correctness, conf_spec_understanding,
    conf_test_adequacy, or None if no baseline has been snapshotted.
    """
    from bob.db import get_feature

    feature = get_feature(feature_id)
    if feature is None:
        return None

    if not feature.readiness_components:
        return None

    try:
        data = json.loads(feature.readiness_components)
    except (json.JSONDecodeError, TypeError):
        return None

    return data.get("baseline_confidence")


def restore_baseline_confidence(feature_id: str) -> None:
    """Rewrite live conf_* columns from the stored baseline snapshot.

    Called by the F-R7-479 auto-reset path when a feature transitions
    needs_human → ready due to an infra-only verdict.

    Raises ValueError if the feature does not exist or if no baseline
    snapshot has been stored for it.
    """
    from bob.db import update_feature

    baseline = get_baseline_confidence(feature_id)
    if baseline is None:
        raise ValueError(
            f"Cannot restore baseline: no baseline snapshot found for feature {feature_id!r}. "
            "Call snapshot_baseline_confidence() at feature creation."
        )

    update_feature(
        feature_id,
        conf_impl_correctness=baseline["conf_impl_correctness"],
        conf_spec_understanding=baseline["conf_spec_understanding"],
        conf_test_adequacy=baseline["conf_test_adequacy"],
    )
    logger.info(
        "readiness_recompute: restored baseline confidence for feature %s: %s",
        feature_id[:8],
        baseline,
    )
