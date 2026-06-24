"""bob77.orchestrator — gate-blocked feature re-synthesis orchestration.

Provides ``handle_gate_blocked_feature``, the canonical entry point for the
promotion sweep to attempt exactly one AC re-synthesis for a gate-blocked
feature, bounded to one attempt per feature per process.

Root cause closed by this module
---------------------------------
When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The old loop re-dispatched it to test-writer/CodeT which rebuild
code — but spec_quality score depends on the ACCEPTANCE CRITERIA, not the
code. Rebuilding code can never raise the score. The fix: when the promotion
sweep finds a gate-blocked feature, call score_gate_loop + synthesize_for_feature
to regenerate its ACs, then re-score. Bounded to ONE attempt per feature per
process via the in-memory _resynthesized_ids set so a feature that still can't
clear 0.85 is left blocked without infinite re-spinning (livelock prevention).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from bob.spec_synthesizer import (
    score_gate_loop,   # noqa: F401 — re-exported for AC surface
    synthesize_for_feature,  # noqa: F401 — re-exported for AC surface
)

logger = logging.getLogger(__name__)

# In-memory set: feature_ids that have already had one re-synthesis attempt
# this process. Cleared only by resetting the process.
_resynthesized_ids: set[str] = set()


def mark_resynthesized(feature_id: str) -> None:
    """Record that feature_id has been re-synthesized once this process.

    After calling this, handle_gate_blocked_feature will return (None, 0.0)
    for this feature_id without re-running the synthesizer. This prevents
    the livelock where gate-blocked features loop endlessly.

    Args:
        feature_id: Non-empty string identifier for the feature.

    Raises:
        TypeError: If feature_id is not a string.
        ValueError: If feature_id is empty.
    """
    if not isinstance(feature_id, str):
        raise TypeError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    _resynthesized_ids.add(feature_id)


def is_resynthesized(feature_id: str) -> bool:
    """Return True if feature_id has already been re-synthesized this process.

    Args:
        feature_id: The feature identifier to check.

    Returns:
        True if mark_resynthesized has been called for this feature_id.
    """
    return feature_id in _resynthesized_ids


def handle_gate_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: Path | None = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> tuple[list[str] | None, float]:
    """Attempt exactly one AC re-synthesis for a gate-blocked feature.

    When the promotion sweep finds a feature whose spec_quality score is below
    the gate threshold (composite < 0.85), this function regenerates its
    acceptance criteria via the score-gate synthesizer loop. Bounded to ONE
    attempt per feature per process: if feature_id is already in the
    _resynthesized_ids set, returns (None, 0.0) immediately without
    re-running the synthesizer.

    The promotion sweep is synchronous, so this runs the async synthesizer in
    a private event loop (asyncio.new_event_loop).

    Args:
        feature_id: Unique identifier of the gate-blocked feature. Must be a
            non-empty string.
        name: Feature name / title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier (passed through to synthesizer). Must
            be a non-empty string.
        workspace: Optional workspace path (passed through to synthesizer).
        synthesize_fn: Optional override for the synthesizer callable.
            Defaults to bob.spec_synthesizer.synthesize_for_feature.
        score_gate_fn: Optional override for the score-gate loop callable.
            Defaults to bob.spec_synthesizer.score_gate_loop.

    Returns:
        (new_acs, new_composite) if re-synthesis produced criteria that cleared
        the gate, or (None, 0.0) if already attempted or synthesis failed.

    Raises:
        ValueError: If feature_id or project_id are not non-empty strings.
        TypeError: If feature_id is not a string.
    """
    if not isinstance(feature_id, str):
        raise TypeError(
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

    # Livelock prevention: exactly one attempt per feature per process
    if feature_id in _resynthesized_ids:
        return None, 0.0

    mark_resynthesized(feature_id)

    _synthesize_fn = synthesize_fn
    _score_gate_fn = score_gate_fn
    if _synthesize_fn is None or _score_gate_fn is None:
        try:
            from bob.spec_synthesizer import (
                score_gate_loop as _sgl,
                synthesize_for_feature as _sff,
            )
            if _synthesize_fn is None:
                _synthesize_fn = _sff
            if _score_gate_fn is None:
                _score_gate_fn = _sgl
        except Exception as exc:
            logger.warning("handle_gate_blocked_feature: import of synthesizer failed: %s", exc)
            return None, 0.0

    try:
        loop = asyncio.new_event_loop()
        try:
            report = loop.run_until_complete(
                _score_gate_fn(
                    synthesize_fn=_synthesize_fn,
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
            "handle_gate_blocked_feature: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0


__all__ = [
    "score_gate_loop",
    "synthesize_for_feature",
    "handle_gate_blocked_feature",
    "mark_resynthesized",
    "is_resynthesized",
]
