"""Gate-blocked feature mid-run AC re-synthesis (feature 077582eb).

Root cause of the "scoring never increases" livelock: when a feature fails the
spec_quality gate (composite < 0.85) it stays 'pending'. The run loop's only
recovery was to re-dispatch it to test-writer/CodeT — which rebuild CODE. But
the spec_quality score is a function of the ACCEPTANCE CRITERIA, not the code,
so rebuilding code can NEVER raise it. The feature loops the same
blocked -> test-writer -> CodeT cycle forever.

Fix: when the promotion sweep finds a gate-blocked feature, RE-RUN the
score-gate synthesizer on it to regenerate its acceptance criteria, then
re-score. Bounded to ONE re-synthesis per feature per process (in-memory set)
so a feature that still can't reach 0.85 after re-synthesis is left blocked
WITHOUT re-spinning — no livelock.

This module is the AC-named entry point (bob.gate_blocked_resynth). The
underlying implementation and the shared one-attempt-per-process set live in
``bob73.gate_blocker`` so the orchestrator and both façades agree on which
features have already been attempted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob73.gate_blocker import (
    _synthesis_attempted,
    mark_synthesis_attempted,
    re_synthesize_gate_blocked_feature as _re_synthesize_gate_blocked_feature,
)

__all__ = [
    "resynthesize_gate_blocked_feature",
    "has_resynthesized",
    "mark_synthesis_attempted",
]


def has_resynthesized(feature_id: str) -> bool:
    """Return True if this feature has already had a re-synthesis attempt.

    A feature is bounded to exactly one AC re-synthesis per process. Once
    attempted, it is left blocked (eventually needs_human) rather than
    re-looped — this is what prevents the livelock.

    Args:
        feature_id: The feature's unique identifier string.

    Returns:
        True if re-synthesis has already been attempted for this feature_id.

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    return feature_id in _synthesis_attempted


def resynthesize_gate_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: Path | None = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> tuple[list[str] | None, float]:
    """Regenerate a gate-blocked feature's ACs via the score-gate synthesizer.

    Bounded to one re-synthesis per feature per process. If this feature has
    already been attempted, returns ``(None, 0.0)`` immediately without
    re-running the synthesizer — the orchestrator MUST NOT repeatedly
    re-dispatch a gate-blocked feature to the implementer.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
        name: Feature name / title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier (passed through to synthesizer).
        workspace: Optional workspace path (passed through to synthesizer).
        synthesize_fn: Optional override for the synthesizer callable.
        score_gate_fn: Optional override for the score-gate loop callable.

    Returns:
        ``(new_acs, new_composite)`` if re-synthesis produced criteria, or
        ``(None, 0.0)`` if already attempted or synthesis failed.

    Raises:
        ValueError: If feature_id, name, or project_id are not non-empty strings.
    """
    return _re_synthesize_gate_blocked_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        project_id=project_id,
        workspace=workspace,
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
