"""Composite spec_quality_score — 8 sub-metrics, weighted geometric mean, 0.65/0.80 gate.

Replaces the F-R7-413 placeholder with a weighted geometric mean of 8 sub-metrics:

  - smell_density        (weight 0.20)
  - predicate_coverage   (weight 0.20)
  - contract_completeness (weight 0.15)
  - boundary_coverage    (weight 0.10)
  - error_path_coverage  (weight 0.10)
  - traceability         (weight 0.10)
  - spec_executability   (weight 0.10)
  - ac_atomicity         (weight 0.05)

Gate semantics:
  score < 0.65  → gate='refuse'  (plan --create is rejected)
  0.65 ≤ score < 0.80 → gate='warn'
  score >= 0.80 → gate='green'
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Literal

# Weights for the 8 sub-metrics. Must sum to 1.0.
SUB_METRIC_WEIGHTS: Dict[str, float] = {
    "smell_density": 0.20,
    "predicate_coverage": 0.20,
    "contract_completeness": 0.15,
    "boundary_coverage": 0.10,
    "error_path_coverage": 0.10,
    "traceability": 0.10,
    "spec_executability": 0.10,
    "ac_atomicity": 0.05,
}

_REFUSE_THRESHOLD = 0.65
_WARN_THRESHOLD = 0.80


@dataclass(frozen=True)
class CompositeScoreResult:
    """Result of the composite spec quality score computation."""

    score: float
    gate: Literal["green", "warn", "refuse"]

    def to_dict(self) -> Dict[str, object]:
        return {"score": self.score, "gate": self.gate}


def calculate_geometric_mean(values: Dict[str, float], weights: Dict[str, float]) -> float:
    """Compute the weighted geometric mean of *values* using *weights*.

    Parameters
    ----------
    values:
        Mapping from metric name to its score in [0, 1].
    weights:
        Mapping from metric name to its weight. Must cover all keys in *values*.

    Returns
    -------
    float
        Weighted geometric mean, clamped to [0.0, 1.0].

    Raises
    ------
    ValueError
        When *values* or *weights* is empty, or when a required key is missing
        from *weights*.
    """
    if not values:
        raise ValueError("values dict must not be empty.")
    if not weights:
        raise ValueError("weights dict must not be empty.")

    missing = set(values.keys()) - set(weights.keys())
    if missing:
        raise ValueError(f"No weight defined for metric(s): {missing!r}")

    log_sum = 0.0
    for key, val in values.items():
        w = weights[key]
        clamped = min(1.0, max(0.0, float(val)))
        if clamped == 0.0:
            return 0.0
        log_sum += w * math.log(clamped)

    result = math.exp(log_sum)
    return min(1.0, max(0.0, result))


def _apply_gate(score: float) -> str:
    if score >= _WARN_THRESHOLD:
        return "green"
    if score >= _REFUSE_THRESHOLD:
        return "warn"
    return "refuse"


def score_gate_decision(score: float) -> str:
    """Return the gate label for a given composite score.

    Parameters
    ----------
    score:
        The composite spec quality score in [0, 1].

    Returns
    -------
    str
        One of ``'refuse'``, ``'warn'``, or ``'green'``.
    """
    return _apply_gate(score)


def compute_spec_quality_score(
    metrics: Dict[str, float],
) -> Dict[str, object]:
    """Alias for compute_composite_score — used by boundary and error test suites."""
    return compute_composite_score(metrics)


def compute_composite_score(
    metrics: Dict[str, float],
) -> Dict[str, object]:
    """Compute the composite spec quality score from the 8 required sub-metrics.

    Implements the weighted geometric mean gate that replaces F-R7-413.
    Score < 0.65 refuses plan --create; 0.65-0.80 warns; >= 0.80 is green.

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].
        All 8 keys must be present; extra keys are ignored.

    Returns
    -------
    dict
        ``{"score": float, "gate": "green" | "warn" | "refuse"}``

    Raises
    ------
    ValueError
        When any required sub-metric key is absent.
    """
    required = set(SUB_METRIC_WEIGHTS.keys())
    provided = set(metrics.keys()) if metrics is not None else set()
    missing = required - provided
    if missing:
        raise ValueError(
            f"Missing required sub-metric(s): {sorted(missing)!r}. "
            f"All 8 sub-metrics must be provided."
        )

    sub_values = {k: metrics[k] for k in required}
    score = calculate_geometric_mean(sub_values, SUB_METRIC_WEIGHTS)
    gate = _apply_gate(score)
    return {"score": float(score), "gate": gate}
