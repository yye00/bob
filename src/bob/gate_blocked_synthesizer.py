"""Gate-blocked feature re-synthesis — canonical entry point (feature adb882e4).

Root cause of the "scoring never increases" livelock:
When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The run loop's only recovery was to re-dispatch to test-writer/CodeT,
which rebuild CODE. But the spec_quality score is a function of ACCEPTANCE
CRITERIA, not code — rebuilding code can never raise the score. The feature
loops the same blocked→test-writer→CodeT cycle forever.

Fix: when the promotion sweep finds a gate-blocked feature, RE-RUN THE
SCORE-GATE SYNTHESIZER on it to regenerate its acceptance criteria, then
re-score. If the new ACs clear the gate, the caller persists them and promotes.
Bounded to ONE re-synthesis per feature per process (module-level set) so a
feature that still cannot reach 0.85 after re-synthesis is left blocked without
re-spinning — no livelock.

Public API:
    re_synthesize_blocked_feature(feature_id, name, description, project_id)
        — attempt one AC re-synthesis for a gate-blocked feature.
    is_resynthesis_attempted(feature_id)
        — idempotency predicate.
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
_resynthesis_attempted: set[str] = set()


def is_resynthesis_attempted(feature_id: str) -> bool:
    """Return True if a re-synthesis has already been attempted for this feature.

    Args:
        feature_id: The feature's unique identifier string.

    Returns:
        True when a re-synthesis attempt has been recorded for *feature_id*,
        False otherwise (including when *feature_id* is empty or not a str).
    """
    if not isinstance(feature_id, str) or not feature_id:
        return False
    return feature_id in _resynthesis_attempted


def _mark_attempted(feature_id: str) -> None:
    _resynthesis_attempted.add(feature_id)


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
    regenerate its acceptance criteria, then re-scores. If the new ACs clear
    the gate, the caller should persist them and promote the feature.

    Bounded to ONE attempt per feature per process via the module-level
    ``_resynthesis_attempted`` set — prevents the livelock where gate-blocked
    features cycle the blocked→test-writer→CodeT path forever without the
    score rising.

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
            "gate_blocked_synthesizer: already attempted %s — skipping to prevent livelock",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
        )
        return None, 0.0

    _mark_attempted(feature_id)

    try:
        if synthesize_fn is None or score_gate_fn is None:
            from bob.spec_synthesizer import (  # noqa: PLC0415
                score_gate_loop as _sgl,
                synthesize_for_feature as _sff,
            )
            if synthesize_fn is None:
                synthesize_fn = _sff
            if score_gate_fn is None:
                score_gate_fn = _sgl
    except Exception as exc:
        logger.warning("gate_blocked_synthesizer: import of synthesizer failed: %s", exc)
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
            "gate_blocked_synthesizer: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0


def resynthesize_gate_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: Path | None = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> tuple[list[str] | None, float]:
    """Alias for re_synthesize_blocked_feature — canonical AC-required name.

    See ``re_synthesize_blocked_feature`` for full documentation.
    """
    return re_synthesize_blocked_feature(
        feature_id=feature_id,
        name=name,
        description=description,
        project_id=project_id,
        workspace=workspace,
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )


def mark_resynthesized(feature_id: str) -> None:
    """Mark feature_id as having been resynthesized (public alias for _mark_attempted).

    Args:
        feature_id: The feature's unique identifier string (non-empty).

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError(f"feature_id must be a non-empty str, got {feature_id!r}")
    _mark_attempted(feature_id)


__all__ = [
    "re_synthesize_blocked_feature",
    "resynthesize_gate_blocked_feature",
    "is_resynthesis_attempted",
    "mark_resynthesized",
]
