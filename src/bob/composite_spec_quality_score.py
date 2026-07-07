"""Composite spec_quality_score — 8 sub-metrics, weighted geometric mean, 0.65/0.80 gate.

Replaces the F-R7-413 placeholder with a weighted geometric mean of 8 sub-metrics:

  - smell_density         (weight 0.20)
  - predicate_coverage    (weight 0.20)
  - contract_completeness (weight 0.15)
  - boundary_coverage     (weight 0.10)
  - error_path_coverage   (weight 0.10)
  - traceability          (weight 0.10)
  - spec_executability    (weight 0.10)
  - ac_atomicity          (weight 0.05)

Gate semantics:
  score < 0.65        → 'refuse'  (plan --create is rejected)
  0.65 <= score < 0.80 → 'warn'
  score >= 0.80        → 'green'

A weighted geometric mean is used (rather than an arithmetic mean) so that a low
value on any single sub-metric drags the overall score down disproportionately: a
spec cannot compensate for zero boundary coverage by scoring perfectly elsewhere.
A zero on any sub-metric collapses the composite to 0.0.
"""

from __future__ import annotations

import math
from typing import Dict, Literal, Mapping, Union

__all__ = [
    "SUB_METRIC_WEIGHTS",
    "REFUSE_THRESHOLD",
    "WARN_THRESHOLD",
    "spec_quality_score",
    "spec_quality_gate",
]

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

REFUSE_THRESHOLD = 0.65
WARN_THRESHOLD = 0.80

GateLabel = Literal["green", "warn", "refuse"]


def spec_quality_score(metrics: Mapping[str, float]) -> float:
    """Compute the composite spec quality score as a weighted geometric mean.

    Parameters
    ----------
    metrics:
        Mapping from each of the 8 sub-metric names to a value in [0, 1]. All 8
        keys must be present; values outside [0, 1] are clamped. Extra keys are
        ignored.

    Returns
    -------
    float
        The weighted geometric mean in [0.0, 1.0].

    Raises
    ------
    ValueError
        When *metrics* is not a mapping, or when any of the 8 required
        sub-metrics is missing.
    """
    if not isinstance(metrics, Mapping):
        raise ValueError(
            f"metrics must be a mapping of sub-metric name to value, "
            f"got {type(metrics).__name__}."
        )

    missing = set(SUB_METRIC_WEIGHTS) - set(metrics)
    if missing:
        raise ValueError(
            f"Missing required sub-metric(s): {sorted(missing)!r}. "
            f"All 8 sub-metrics must be provided."
        )

    log_sum = 0.0
    for name, weight in SUB_METRIC_WEIGHTS.items():
        value = min(1.0, max(0.0, float(metrics[name])))
        if value == 0.0:
            return 0.0
        log_sum += weight * math.log(value)

    score = math.exp(log_sum)
    return min(1.0, max(0.0, score))


def spec_quality_gate(score_or_metrics: Union[float, Mapping[str, float]]) -> GateLabel:
    """Map a composite score (or metrics mapping) to a gate label.

    Parameters
    ----------
    score_or_metrics:
        Either a precomputed composite score (a real number), or a mapping of
        the 8 sub-metrics from which the score is computed via
        :func:`spec_quality_score`.

    Returns
    -------
    str
        ``'green'`` when score >= 0.80, ``'warn'`` when 0.65 <= score < 0.80,
        ``'refuse'`` when score < 0.65. A ``'refuse'`` gate rejects
        ``plan --create``.

    Raises
    ------
    ValueError
        When *score_or_metrics* is neither a mapping nor a real number.
    """
    if isinstance(score_or_metrics, Mapping):
        score = spec_quality_score(score_or_metrics)
    elif isinstance(score_or_metrics, bool):
        # bool is an int subclass but is never a valid score input.
        raise ValueError("score must be a real number, not a bool.")
    elif isinstance(score_or_metrics, (int, float)):
        score = float(score_or_metrics)
    else:
        raise ValueError(
            f"spec_quality_gate expects a score (float) or metrics mapping, "
            f"got {type(score_or_metrics).__name__}."
        )

    if score >= WARN_THRESHOLD:
        return "green"
    if score >= REFUSE_THRESHOLD:
        return "warn"
    return "refuse"
