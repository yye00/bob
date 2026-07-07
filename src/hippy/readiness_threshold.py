"""Env-overridable readiness-claim threshold (dc2a0f06 / 9ec1f44d).

The claim gate normally requires ``readiness_score >= per-risk threshold``
(low .70 / medium .80 / high .90 / critical .95). When ``spec_quality_score``
is absent (None) — e.g. the project's ``tools/spec_quality_score.py`` is not
importable in the workspace — readiness falls back to a low AC-count heuristic
and genuinely-ready features sit below the 0.80 medium gate forever. That is the
F-R7-564 readiness deadlock resurfacing through a missing scorer, collapsing
concurrency to ~1 executing feature.

Fix: ``BOB_READINESS_THRESHOLD``, when set to a float in ``[0, 1]``, REPLACES
the per-risk thresholds with a single floor for all risk categories. It is read
lazily on each claim so an operator can unstick a running build without a code
edit. An unset/out-of-range/malformed value is ignored, leaving the per-risk
defaults exactly as before. Dependency gating is unaffected.

This module is the hippy-side façade. The concrete atomic claim lives in
:mod:`bob.orchestrator.feature_claim`; the scheduler wiring is
:mod:`hippy.scheduler`.
"""

from __future__ import annotations

from bob.orchestrator.feature_claim import (
    parse_readiness_threshold,
    resolve_readiness_override,
)
from hippy.scheduler import (
    claim_next_ready_feature,
    resolve_readiness_floor,
)

__all__ = [
    "resolve_readiness_threshold",
    "claim_next_ready_feature",
    "parse_readiness_threshold",
    "resolve_readiness_override",
    "resolve_readiness_floor",
]


def resolve_readiness_threshold(
    risk_category: str = "medium",
    env: dict | None = None,
) -> float:
    """Resolve the effective readiness floor for a claim.

    When ``BOB_READINESS_THRESHOLD`` holds a valid float in ``[0, 1]``, that
    value is returned as the single floor for every risk category. Otherwise the
    per-risk default for *risk_category* applies (unknown categories fall back to
    the medium default of 0.80).

    An unset, empty, malformed, or out-of-range override is silently ignored —
    it never raises and never returns a bogus floor that would corrupt gating.
    Use :func:`parse_readiness_threshold` for the strict, raising parse.

    Args:
        risk_category: One of ``low``/``medium``/``high``/``critical``.
        env: Optional mapping to read the override from (for testing);
            defaults to ``os.environ``.

    Returns:
        The readiness floor in ``[0, 1]``.
    """
    if not isinstance(risk_category, str):
        raise ValueError(
            f"risk_category must be a str, got {type(risk_category).__name__}"
        )
    return resolve_readiness_floor(risk_category, env)
