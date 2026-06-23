"""Gate-blocked feature re-synthesis entry point for bob74.orchestrator.

Exposes ``gate_blocked_feature_resynthesis`` — the orchestrator-level function
that triggers AC re-synthesis for features blocked by the spec_quality gate.

This is the recovery path for the pre-execution gate livelock:
  blocked → test-writer → CodeT → (score never rises) → repeat forever

Fix: the orchestrator's promotion sweep calls this to re-run
score_gate_loop on the feature, regenerating its ACs and re-scoring.
Bounded to ONE attempt per feature per process via bob73.gate_blocker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def gate_blocked_feature_resynthesis(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: Path | None = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> tuple[list[str] | None, float]:
    """Re-synthesize ACs for a gate-blocked feature (one attempt per process).

    Delegates to :func:`bob73.gate_blocker.re_synthesize_gate_blocked_feature`.
    Returns ``(new_acs, composite)`` on success or ``(None, 0.0)`` if the
    feature already had a synthesis attempt or synthesis failed.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
        name: Feature name / title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier passed through to the synthesizer.
        workspace: Optional workspace path passed through to the synthesizer.
        synthesize_fn: Optional synthesizer callable override.
        score_gate_fn: Optional score-gate loop callable override.

    Returns:
        ``(new_acs, new_composite)`` if synthesis produced criteria, or
        ``(None, 0.0)`` if already attempted or synthesis failed.

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    from bob73.gate_blocker import re_synthesize_gate_blocked_feature

    return re_synthesize_gate_blocked_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        project_id=project_id,
        workspace=workspace,
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
