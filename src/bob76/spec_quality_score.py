"""bob76.spec_quality_score — composite spec quality score with 8 sub-metrics.

Wraps spec_quality.composite_score to provide a bob76-scoped API that:

  - computes the weighted geometric mean of 8 sub-metrics
  - applies the 0.65/0.80 gate thresholds
  - integrates with the planner (plan --create is refused when score < 0.65)

Sub-metric weights
------------------
  smell_density        (0.20)
  predicate_coverage   (0.20)
  contract_completeness (0.15)
  boundary_coverage    (0.10)
  error_path_coverage  (0.10)
  traceability         (0.10)
  spec_executability   (0.10)
  ac_atomicity         (0.05)

Gate thresholds
---------------
  score < 0.65  → refuse  (plan --create blocked)
  0.65 ≤ score < 0.80  → warn
  score ≥ 0.80  → green
"""

from __future__ import annotations

from typing import Dict, Literal

from spec_quality.composite_score import (
    SUB_METRIC_WEIGHTS,
    compute_spec_quality_score as _compute_spec_quality_score,
)

GateLabel = Literal["green", "warn", "refuse"]

_REFUSE_THRESHOLD = 0.65
_WARN_THRESHOLD = 0.80


def compute_composite_score(metrics: Dict[str, float]) -> Dict[str, object]:
    """Compute the composite spec quality score from 8 sub-metrics.

    Uses a weighted geometric mean of the 8 required sub-metric scores.
    Values outside [0, 1] are clamped. A zero value in any metric drives
    the entire score to 0.0 (geometric mean property).

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].
        All 8 keys must be present.

    Returns
    -------
    dict
        ``{"score": float, "gate": "green" | "warn" | "refuse"}``

    Raises
    ------
    ValueError
        When any required sub-metric key is absent or the input is invalid.
    TypeError
        When metrics is not a dict-like object.
    """
    return _compute_spec_quality_score(metrics)


def validate_score_gate(
    metrics: Dict[str, float],
) -> tuple[bool, str | None]:
    """Validate whether the composite score passes the gate for plan creation.

    Computes the composite score and checks it against the 0.65/0.80 thresholds.
    The planner calls this before ``plan --create`` to enforce the spec quality gate.

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].
        All 8 keys must be present.

    Returns
    -------
    tuple[bool, str | None]
        ``(passed, message)`` where:
        - ``passed`` is True when the gate is "warn" or "green" (score >= 0.65)
        - ``message`` is None when passed, or a human-readable refusal reason
          when score < 0.65.

    Raises
    ------
    ValueError
        When any required sub-metric key is absent.
    """
    result = compute_composite_score(metrics)
    score: float = result["score"]  # type: ignore[assignment]
    gate: str = result["gate"]  # type: ignore[assignment]

    if gate == "refuse":
        msg = (
            f"Spec quality score {score:.3f} is below the minimum threshold "
            f"{_REFUSE_THRESHOLD} required to create a plan. "
            f"Improve the acceptance criteria to raise the score."
        )
        return False, msg

    return True, None


__all__ = [
    "SUB_METRIC_WEIGHTS",
    "compute_composite_score",
    "validate_score_gate",
    "_REFUSE_THRESHOLD",
    "_WARN_THRESHOLD",
]
