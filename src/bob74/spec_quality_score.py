"""Composite spec_quality_score for bob74.

Public API for the 8-sub-metric weighted geometric mean scorer.
Replaces the F-R7-413 placeholder.

Sub-metric weights:
    smell_density        (0.20)
    predicate_coverage   (0.20)
    contract_completeness (0.15)
    boundary_coverage    (0.10)
    error_path_coverage  (0.10)
    traceability         (0.10)
    spec_executability   (0.10)
    ac_atomicity         (0.05)

Gate thresholds:
    score < 0.65  → refuse (plan --create blocked)
    0.65 ≤ score < 0.80 → warn
    score ≥ 0.80  → green
"""

from __future__ import annotations

from typing import Dict, Literal

from spec_quality.composite_score import (
    SUB_METRIC_WEIGHTS,
    compute_spec_quality_score,
)

GateLabel = Literal["green", "warn", "refuse"]

_GATE_REFUSE = 0.65
_GATE_WARN = 0.80


def calculate_composite_score(metrics: Dict[str, float]) -> float:
    """Compute the composite spec quality score from the 8 required sub-metrics.

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].
        All 8 keys must be present.

    Returns
    -------
    float
        Composite score in [0.0, 1.0] computed as weighted geometric mean.

    Raises
    ------
    ValueError
        When any required sub-metric key is absent or input is invalid.
    """
    result = compute_spec_quality_score(metrics)
    return float(result["score"])


def apply_quality_gate(score: float) -> GateLabel:
    """Map a composite score to a gate label for plan --create enforcement.

    Parameters
    ----------
    score:
        Composite spec quality score in [0.0, 1.0].

    Returns
    -------
    "refuse"  if score < 0.65  (plan --create is blocked)
    "warn"    if 0.65 <= score < 0.80
    "green"   if score >= 0.80
    """
    if score >= _GATE_WARN:
        return "green"
    if score >= _GATE_REFUSE:
        return "warn"
    return "refuse"


__all__ = [
    "SUB_METRIC_WEIGHTS",
    "calculate_composite_score",
    "apply_quality_gate",
]
