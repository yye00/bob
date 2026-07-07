"""hippy scheduler — claim-gate wiring for the env-overridable readiness floor.

The scheduler decides which ready feature a worker may claim next. Its readiness
floor is normally the per-risk threshold (low .70 / medium .80 / high .90 /
critical .95). When ``BOB_READINESS_THRESHOLD`` is set to a float in ``[0, 1]``,
that single floor REPLACES the per-risk thresholds for all risk categories —
the manual escape hatch for the F-R7-564 readiness deadlock where an absent
``spec_quality_score`` leaves genuinely-ready features stuck below the medium
gate and collapses concurrency to ~1.

The concrete claim implementation lives in :mod:`bob.orchestrator.feature_claim`
(the atomic SQLite claim). This module is the hippy-side entry point that the
readiness-threshold façade wires into.
"""

from __future__ import annotations

from bob.orchestrator.feature_claim import (
    claim_next_ready_feature as _claim_next_ready_feature,
)
from bob.orchestrator.feature_claim import (
    parse_readiness_threshold,
    resolve_readiness_override,
)

__all__ = [
    "claim_next_ready_feature",
    "parse_readiness_threshold",
    "resolve_readiness_override",
    "resolve_readiness_floor",
]


def resolve_readiness_floor(risk_category: str, env: dict | None = None) -> float:
    """Resolve the effective readiness floor for a given risk category.

    When ``BOB_READINESS_THRESHOLD`` holds a valid float in ``[0, 1]``, that
    value is the floor for EVERY risk category. Otherwise the per-risk default
    applies. An unknown risk category falls back to the medium default (0.80),
    matching the ``ELSE`` branch of the claim SQL.

    Args:
        risk_category: One of ``low``/``medium``/``high``/``critical``.
        env: Optional mapping to read the override from (for testing);
            defaults to ``os.environ``.

    Returns:
        The readiness floor in ``[0, 1]``.
    """
    override = resolve_readiness_override(env)
    if override is not None:
        return override
    per_risk = {
        "low": 0.70,
        "medium": 0.80,
        "high": 0.90,
        "critical": 0.95,
    }
    return per_risk.get(risk_category, 0.80)


def claim_next_ready_feature(*, project_id: str, worker_id: str):
    """Claim the next ready feature, honouring the env readiness override.

    Thin hippy-side delegate to :func:`bob.orchestrator.feature_claim.
    claim_next_ready_feature`, which reads ``BOB_READINESS_THRESHOLD`` lazily
    on each claim.
    """
    return _claim_next_ready_feature(project_id=project_id, worker_id=worker_id)
