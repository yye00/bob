"""Composite spec_quality_score using weighted geometric mean of 8 sub-metrics.

Replaces the F-R7-413 placeholder. The 8 sub-metrics and their weights:

  smell_density        (0.20)
  predicate_coverage   (0.20)
  contract_completeness (0.15)
  boundary_coverage    (0.10)
  error_path_coverage  (0.10)
  traceability         (0.10)
  spec_executability   (0.10)
  ac_atomicity         (0.05)

Gate: score < 0.65 → refuse; 0.65 ≤ score < 0.80 → warn; score ≥ 0.80 → green.
"""

from __future__ import annotations

import math
from typing import Dict, Literal

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

_GATE_REFUSE = 0.65
_GATE_WARN = 0.80

GateLabel = Literal["green", "warn", "refuse"]


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


def _apply_gate(score: float) -> GateLabel:
    if score >= _GATE_WARN:
        return "green"
    if score >= _GATE_REFUSE:
        return "warn"
    return "refuse"


def compute_spec_quality_score(
    metrics: Dict[str, float],
) -> Dict[str, object]:
    """Compute the composite spec quality score from the 8 required sub-metrics.

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
    provided = set(metrics.keys())
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
