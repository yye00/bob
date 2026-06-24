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
from typing import Mapping

# Weights for the 8 sub-metrics. Must sum to 1.0.
SUB_METRIC_WEIGHTS: dict[str, float] = {
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


def composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(
    metrics: Mapping[str, float],
) -> dict[str, object]:
    """Compute the composite spec quality score using a weighted geometric mean.

    Parameters
    ----------
    metrics:
        Mapping from sub-metric name to value in [0, 1]. All 8 sub-metrics
        must be present; values outside [0, 1] are clamped.

    Returns
    -------
    dict with keys:
        - ``score`` (float): weighted geometric mean in [0, 1]
        - ``gate`` (str): one of ``'refuse'``, ``'warn'``, ``'green'``

    Raises
    ------
    KeyError
        When any of the 8 required sub-metrics is missing from *metrics*.
    """
    # Validate all required keys are present
    for key in SUB_METRIC_WEIGHTS:
        if key not in metrics:
            raise KeyError(f"Missing required sub-metric: {key!r}")

    # Weighted geometric mean: exp(sum(w_i * log(v_i)))
    # A zero value in any metric collapses the geometric mean to 0.
    log_sum = 0.0
    for metric, weight in SUB_METRIC_WEIGHTS.items():
        value = float(metrics[metric])
        value = max(0.0, min(1.0, value))  # clamp to [0, 1]
        if value == 0.0:
            score = 0.0
            return {"score": score, "gate": "refuse"}
        log_sum += weight * math.log(value)

    score = math.exp(log_sum)
    score = round(min(1.0, max(0.0, score)), 9)

    if score >= _WARN_THRESHOLD:
        gate = "green"
    elif score >= _REFUSE_THRESHOLD:
        gate = "warn"
    else:
        gate = "refuse"

    return {"score": score, "gate": gate}
