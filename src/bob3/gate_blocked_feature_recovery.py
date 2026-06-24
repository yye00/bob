"""Gate-blocked feature recovery module (feature 36b33b52).

Root cause of the "scoring never increases" livelock:
When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The run loop's only recovery was to re-dispatch it to
test-writer/CodeT, which rebuild CODE. But the spec_quality score is a
function of the ACCEPTANCE CRITERIA, not the code — rebuilding code can never
raise the score.

Fix: when the promotion sweep finds a gate-blocked feature, RE-RUN THE
SCORE-GATE SYNTHESIZER on it to regenerate its acceptance criteria, then
re-score. Bounded to ONE re-synthesis per feature per process (module-level
set) so a feature that still cannot reach 0.85 after re-synthesis is left
blocked WITHOUT re-spinning — no livelock.

Public API:
    synthesize_blocked_feature_ac(feature_id, name, description, project_id)
        — attempt one AC re-synthesis for a gate-blocked feature.
    mark_re_synthesized(feature_id)
        — record that re-synthesis has been attempted for a feature.
    is_gate_blocked(composite_score, threshold=0.85)
        — return True when a composite score is below the gate threshold.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level set: one re-synthesis attempt per feature per process.
# Prevents the livelock where gate-blocked features cycle forever through
# the blocked→test-writer→CodeT path without the score ever rising.
_re_synthesized: set[str] = set()

_GATE_THRESHOLD = 0.85


def is_gate_blocked(composite_score: float, threshold: float = _GATE_THRESHOLD) -> bool:
    """Return True when composite_score is below the spec-quality gate threshold.

    Args:
        composite_score: The feature's composite spec-quality score (0.0–1.0).
        threshold: The gate threshold (default 0.85).

    Returns:
        True when composite_score < threshold, False otherwise.

    Raises:
        ValueError: If composite_score or threshold are not numeric.
    """
    if not isinstance(composite_score, (int, float)):
        raise ValueError(
            f"composite_score must be numeric, got {type(composite_score).__name__!r}"
        )
    if not isinstance(threshold, (int, float)):
        raise ValueError(
            f"threshold must be numeric, got {type(threshold).__name__!r}"
        )
    return float(composite_score) < float(threshold)


def mark_re_synthesized(feature_id: str) -> None:
    """Record that re-synthesis has been attempted for this feature.

    After calling this, ``synthesize_blocked_feature_ac`` will return
    (None, 0.0) for this feature_id without re-running the synthesizer.
    This prevents the livelock where gate-blocked features cycle the
    blocked→test-writer→CodeT path forever without the score rising.

    Args:
        feature_id: The feature's unique identifier string.

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    _re_synthesized.add(feature_id)


def synthesize_blocked_feature_ac(
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
    regenerate its acceptance criteria, then re-scores. If the new ACs clear
    the gate, the caller should persist them and promote the feature.

    Bounded to ONE attempt per feature per process via the module-level
    ``_re_synthesized`` set. If already attempted, returns (None, 0.0)
    immediately without re-running the synthesizer — no livelock.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
        name: Feature name / title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier (passed through to synthesizer).
        workspace: Optional workspace path (passed through to synthesizer).
        synthesize_fn: Optional override for the synthesizer callable.
            Defaults to ``bob3.spec_synthesizer.synthesize_for_feature``.
        score_gate_fn: Optional override for the score-gate loop callable.
            Defaults to ``bob3.spec_synthesizer.score_gate_loop``.

    Returns:
        ``(new_acs, new_composite)`` if re-synthesis produced criteria, or
        ``(None, 0.0)`` if already attempted or synthesis failed.

    Raises:
        ValueError: If feature_id or project_id are not non-empty strings.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    if not isinstance(project_id, str):
        raise ValueError(
            f"project_id must be a str, got {type(project_id).__name__!r}"
        )
    if not project_id:
        raise ValueError("project_id must be non-empty")

    if feature_id in _re_synthesized:
        logger.debug(
            "gate_blocked_feature_recovery: already attempted %s — skipping to prevent livelock",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
        )
        return None, 0.0

    mark_re_synthesized(feature_id)

    try:
        if synthesize_fn is None or score_gate_fn is None:
            from bob3.spec_synthesizer import (  # noqa: PLC0415
                score_gate_loop as _score_gate_loop,
                synthesize_for_feature as _synthesize_for_feature,
            )
            if synthesize_fn is None:
                synthesize_fn = _synthesize_for_feature
            if score_gate_fn is None:
                score_gate_fn = _score_gate_loop
    except Exception as exc:
        logger.warning(
            "gate_blocked_feature_recovery: import of synthesizer failed: %s", exc
        )
        return None, 0.0

    try:
        loop = asyncio.new_event_loop()
        try:
            report = loop.run_until_complete(
                score_gate_fn(
                    synthesize_fn=synthesize_fn,
                    title=name,
                    description=description,
                    project_id=project_id,
                    workspace=workspace,
                )
            )
        finally:
            loop.close()
        if report and report.criteria:
            return report.criteria, float(report.composite or 0.0)
    except Exception as exc:
        logger.warning(
            "gate_blocked_feature_recovery: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0


__all__ = [
    "synthesize_blocked_feature_ac",
    "mark_re_synthesized",
    "is_gate_blocked",
]
