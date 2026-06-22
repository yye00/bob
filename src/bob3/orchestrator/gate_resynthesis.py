"""Gate-blocked feature re-synthesis (066763fc).

Root cause of the livelock: when a feature fails the spec_quality gate
(composite < 0.85) it stays 'pending'. The run loop's only recovery was to
re-dispatch to test-writer/CodeT, which rebuild CODE. But the spec_quality score
depends on the ACCEPTANCE CRITERIA — not the code — so rebuilding code can never
raise the score. The feature loops blocked→test-writer→CodeT forever.

Fix: when the promotion sweep finds a gate-blocked feature, RE-RUN THE SCORE-GATE
SYNTHESIZER on it to regenerate its acceptance criteria, then re-score. If the new
ACs clear the gate, the caller should persist them and promote. Bounded to ONE
re-synthesis per feature per process via ``_resynthesis_attempted`` — no livelock.

Public API:
- ``resynthesized_ac_for_blocked_feature`` — entry point for the orchestrator's
  promotion sweep; attempts exactly one AC re-synthesis per feature per process.
- ``mark_resynthesis_attempted`` — mark a feature as having already been attempted
  (allows callers to pre-mark or test the idempotency boundary).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level set: one re-synthesis attempt per feature per process.
# Prevents the livelock where gate-blocked features cycle the
# blocked→test-writer→CodeT path forever without the score ever rising.
_resynthesis_attempted: set[str] = set()


def mark_resynthesis_attempted(feature_id: str) -> None:
    """Record that a re-synthesis attempt has been made for *feature_id*.

    Args:
        feature_id: The feature's unique identifier string (non-empty).

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    _resynthesis_attempted.add(feature_id)


def resynthesized_ac_for_blocked_feature(
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
    regenerate its acceptance criteria and re-scores. If the new ACs clear the
    gate, the caller should persist them and promote the feature.

    Bounded to ONE attempt per feature per process via ``_resynthesis_attempted``
    — prevents the livelock where gate-blocked features cycle the
    blocked→test-writer→CodeT path forever without the score rising.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
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

    if feature_id in _resynthesis_attempted:
        logger.debug(
            "gate_resynthesis: already attempted %s — skipping to prevent livelock",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
        )
        return None, 0.0

    mark_resynthesis_attempted(feature_id)

    try:
        if synthesize_fn is None or score_gate_fn is None:
            from bob3.spec_synthesizer import (
                score_gate_loop as _sgl,
                synthesize_for_feature as _sff,
            )
            if synthesize_fn is None:
                synthesize_fn = _sff
            if score_gate_fn is None:
                score_gate_fn = _sgl
    except Exception as exc:
        logger.warning("gate_resynthesis: import of synthesizer failed: %s", exc)
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
            "gate_resynthesis: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0


__all__ = [
    "resynthesized_ac_for_blocked_feature",
    "mark_resynthesis_attempted",
]
