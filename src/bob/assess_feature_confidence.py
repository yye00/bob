"""Feature confidence assessment with spec_quality_score mapping.

readiness_score MUST be derived from the DEMONSTRATED spec_quality_score the
feature already earned at the ready-promotion gate, NOT from the conservative
AC-count heuristic that capped readiness at 0.56.

Required mapping (per feature description):
  standalone:  readiness = spec_quality_score * 0.92
  integration: readiness = spec_quality_score * 0.30
  fallback (no composite): use AC-count heuristic

This severs the chicken-and-egg deadlock where features at readiness=0.0 could
never be claimed (claim gate requires readiness >= threshold), never got assessed,
and stayed 0.0 forever.

Lowers no gate: a bare-pass composite (0.85) maps to 0.78, still below the 0.80
medium threshold. Only features with genuinely high-quality specs (composite >=
0.87 for standalone) become claimable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = [
    "assess_with_spec_quality_mapping",
    "assess_feature_confidence",
    "seed_readiness_for_zero_features",
]


def seed_readiness_for_zero_features(project_id: str) -> int:
    """Seed readiness_score for every ready feature that still sits at 0.0.

    Satisfies AC: 'Function defined: bob.assess_feature_confidence.seed_readiness_for_zero_features'.

    This breaks the chicken-and-egg deadlock:
    - ``features_ready`` view requires ``readiness_score >= threshold``
    - ``assess_feature_confidence`` is only called AFTER a feature is claimed
    - Fresh features at 0.0 can never be claimed, never assessed, stay 0.0 forever

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
    from bob.db import get_features_by_project, update_feature  # noqa: PLC0415

    seeded = 0
    features = get_features_by_project(project_id)
    for feature in features:
        if feature.status != "ready":
            continue
        if feature.readiness_score is not None and feature.readiness_score != 0.0:
            continue

        fid = feature.id
        assessment = assess_with_spec_quality_mapping(fid)
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

_INTEGRATION_KEYWORDS = frozenset(
    ["integrate", "hook", "connect", "call", "invoke", "wire"]
)

_STANDALONE_IMPL_FACTOR = 0.92
_INTEGRATION_IMPL_FACTOR = 0.30


def _is_integration_feature(name: str, description: str) -> bool:
    """Return True if the feature's name or description marks it as an integration."""
    combined = (name + " " + description).lower()
    return any(kw in combined for kw in _INTEGRATION_KEYWORDS)


def assess_with_spec_quality_mapping(feature_id: str) -> dict[str, float]:
    """Assess feature confidence using the spec_quality_score mapping.

    Derives ``readiness_score`` from the DEMONSTRATED ``spec_quality_score``
    the feature earned at the ready-promotion gate:

    - standalone features: ``readiness = spec_quality_score * 0.92``
    - integration features: ``readiness = spec_quality_score * 0.30``
    - fallback (no composite yet): AC-count heuristic (same as baseline)

    This mapping removes the unearned 0.0 floor that deadlocked every
    high-quality feature:
    - A bare-pass composite (0.85) yields 0.782 for standalone — just under
      the 0.80 medium gate, demanding a hair more quality.
    - A strong composite (≥0.87) clears the 0.80 gate.
    - Integration features land far below the 0.70 low-risk gate (0.30 ×
      spec_quality_score ≤ 0.30), staying correctly blocked until research runs.

    Parameters
    ----------
    feature_id:
        UUID of the feature to assess.

    Returns
    -------
    dict with keys:
        conf_spec_understanding, conf_impl_correctness, conf_test_adequacy,
        readiness_score — all floats in [0.0, 1.0].
    """
    from bob.db import get_feature  # noqa: PLC0415

    _zero = {
        "conf_spec_understanding": 0.0,
        "conf_impl_correctness": 0.0,
        "conf_test_adequacy": 0.0,
        "readiness_score": 0.0,
    }

    feature = get_feature(feature_id)
    if feature is None:
        return _zero

    import json  # noqa: PLC0415

    # Parse acceptance criteria for AC-count heuristic fallback
    criteria_list: list = []
    if feature.acceptance_criteria:
        try:
            criteria_list = json.loads(feature.acceptance_criteria)
        except (json.JSONDecodeError, TypeError):
            criteria_list = []

    # AC-count heuristic scores
    if len(criteria_list) >= 3:
        spec_score = 0.7
    elif len(criteria_list) >= 1:
        spec_score = 0.5
    else:
        spec_score = 0.2

    is_integration = _is_integration_feature(
        feature.name or "", feature.description or ""
    )

    if is_integration:
        impl_score = 0.3
        spec_score = min(spec_score, 0.5)
    else:
        impl_score = spec_score

    test_score = spec_score * 0.8

    # Derive readiness from the demonstrated spec_quality_score, NOT from
    # the conservative min() of the AC-count heuristic.
    sq = getattr(feature, "spec_quality_score", None)
    if sq is not None and sq > 0.0:
        impl_factor = _INTEGRATION_IMPL_FACTOR if is_integration else _STANDALONE_IMPL_FACTOR
        readiness = round(min(1.0, float(sq) * impl_factor), 10)
    else:
        readiness = min(spec_score, impl_score, test_score)

    return {
        "conf_spec_understanding": spec_score,
        "conf_impl_correctness": impl_score,
        "conf_test_adequacy": test_score,
        "readiness_score": readiness,
    }


def assess_feature_confidence(feature_id: str) -> dict[str, float]:
    """Canonical entry point — delegates to assess_with_spec_quality_mapping.

    Re-exported for callers that import from this module rather than bob.db.
    """
    return assess_with_spec_quality_mapping(feature_id)
