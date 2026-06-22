"""Score-gate synthesizer facade (feature d987030c / 30b01c26).

Exposes ``score_gate_loop`` and ``synthesize_for_feature`` as the canonical
module-level names for gate-blocked feature re-synthesis, delegating to
``bob3.spec_synthesizer``.  This module is the stable import point referenced
by the AC: "File exists: src/bob3/score_gate_synthesizer.py".

Also exposes ``re_synthesize_blocked_feature`` — the single-call entry point
for mid-run re-synthesis of gate-blocked features (feature 30b01c26).

Root cause this fixes (see gate_resynth.py for full narrative):
When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'.  Re-dispatching to test-writer/CodeT only rebuilds CODE, but the
score depends on ACCEPTANCE CRITERIA — rebuilding code can never raise the score.
The correct recovery is to re-synthesize the ACs via score_gate_loop.
Bounded to ONE attempt per feature per process (in-memory set) to prevent
livelock: a feature that cannot reach 0.85 after one re-synthesis is left
blocked (needs_human) and never re-spun.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_synthesizer import (
    ScoreGateReport,  # noqa: F401
    score_gate_loop,  # re-exported as primary entry point
    score_gate_threshold_from_env,  # noqa: F401
    synthesize_for_feature,  # re-exported as primary entry point
)

__all__ = [
    "score_gate_loop",
    "synthesize_for_feature",
    "ScoreGateReport",
    "score_gate_threshold_from_env",
    "re_synthesize_blocked_feature",
]


def re_synthesize_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: Path | None = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> tuple[list[str] | None, float]:
    """Attempt exactly one AC re-synthesis for a gate-blocked feature.

    When the promotion sweep finds a feature blocked by the spec_quality gate
    (composite < 0.85), this function re-runs the score-gate synthesizer to
    regenerate its acceptance criteria and re-score. If the new ACs clear the
    gate, the caller should persist them and promote the feature.

    Delegates to ``bob3.gate_synthesizer.re_synthesize_gate_blocked_feature``
    which maintains the module-level ``_resynthesized`` set that bounds attempts
    to ONE per feature per process — preventing the livelock where gate-blocked
    features cycle the blocked→test-writer→CodeT path indefinitely.

    Args:
        feature_id: Unique identifier of the gate-blocked feature (non-empty str).
        name: Feature name/title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier passed to the synthesizer.
        workspace: Optional workspace path passed to the synthesizer.
        synthesize_fn: Override synthesizer callable (for testing).
        score_gate_fn: Override score-gate loop callable (for testing).

    Returns:
        ``(new_acs, new_composite)`` if re-synthesis produced criteria, or
        ``(None, 0.0)`` if already attempted or synthesis failed.

    Raises:
        ValueError: If feature_id or project_id are not non-empty strings.
    """
    from bob3.gate_synthesizer import re_synthesize_gate_blocked_feature  # noqa: PLC0415

    return re_synthesize_gate_blocked_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        project_id=project_id,
        workspace=workspace,
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
