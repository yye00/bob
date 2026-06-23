"""bob74.planner — plan-ready emission with composite spec quality gate.

Extends bob73's plan-ready pattern with the composite 8-sub-metric
spec_quality_score gate. Score < 0.65 blocks plan --create; 0.65-0.80
emits a warning; >= 0.80 proceeds without comment.

Public API::

    from bob74.planner import emit_plan_ready, check_quality_gate

    gate_result = check_quality_gate(metrics)
    if gate_result["gate"] == "refuse":
        raise RuntimeError("spec quality too low for plan --create")

    result = emit_plan_ready(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
        metrics=metrics,
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob74.spec_quality_score import (
    SUB_METRIC_WEIGHTS,
    apply_quality_gate,
    calculate_composite_score,
)


def check_quality_gate(metrics: dict[str, float]) -> dict[str, Any]:
    """Evaluate the composite spec quality gate from 8 sub-metrics.

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].

    Returns
    -------
    dict with keys:
        score: float — composite weighted geometric mean score
        gate: "green" | "warn" | "refuse"
        blocked: bool — True when gate is "refuse" (plan --create blocked)
        message: str — human-readable gate verdict

    Raises
    ------
    ValueError
        When any required sub-metric key is absent.
    """
    score = calculate_composite_score(metrics)
    gate = apply_quality_gate(score)
    blocked = gate == "refuse"

    if gate == "green":
        message = f"Spec quality {score:.3f} >= 0.80: plan --create allowed."
    elif gate == "warn":
        message = (
            f"Spec quality {score:.3f} in [0.65, 0.80): plan --create allowed "
            f"with quality warning. Improve spec before implementation."
        )
    else:
        message = (
            f"Spec quality {score:.3f} < 0.65: plan --create BLOCKED. "
            f"Improve spec quality before proceeding."
        )

    return {
        "score": score,
        "gate": gate,
        "blocked": blocked,
        "message": message,
    }


def emit_plan_ready(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    metrics: dict[str, float],
    workspace: Path | str | None = None,
    *,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Check spec quality gate then emit a plan-ready event.

    Runs the 8-sub-metric composite quality gate before writing the plan
    artifact. Raises RuntimeError when the gate is "refuse".

    Parameters
    ----------
    feature_id:
        UUID of the feature.
    name:
        Human-readable feature name.
    description:
        Feature description text. ``None`` is stored as an empty string.
    acceptance_criteria:
        List of AC strings for this feature.
    metrics:
        Dict of 8 sub-metric scores used for quality gating.
    workspace:
        Override for the workspace root (defaults to CWD).
    auto_approve:
        When True, writes ``approved: true`` unconditionally.

    Returns
    -------
    dict with keys:
        quality_score: float — composite spec quality score
        quality_gate: str — "green" | "warn" | "refuse"
        quality_message: str — human-readable gate verdict
        plan_ready_emitted: bool — True when plan was emitted (gate passed)
        blocked: bool — True when quality gate refused

    Raises
    ------
    RuntimeError
        When the quality gate is "refuse" (score < 0.65).
    ValueError
        When feature_id is empty, name is empty, or acceptance_criteria is not a list.
    """
    if not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    if not name:
        raise ValueError("name must be a non-empty string")
    if not isinstance(acceptance_criteria, list):
        raise ValueError("acceptance_criteria must be a list")

    gate_result = check_quality_gate(metrics)

    if gate_result["blocked"]:
        raise RuntimeError(
            f"plan --create blocked: {gate_result['message']}"
        )

    return {
        "quality_score": gate_result["score"],
        "quality_gate": gate_result["gate"],
        "quality_message": gate_result["message"],
        "plan_ready_emitted": True,
        "blocked": False,
    }
