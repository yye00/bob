"""Gate-blocked feature re-synthesis module (feature d5671a1a).

Root cause of the livelock:
When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The run loop's only recovery was to re-dispatch to test-writer/CodeT,
which rebuild CODE. But the spec_quality score is a function of the ACCEPTANCE
CRITERIA, not the code — rebuilding code can never raise the score. This module
provides the correct recovery: attempt one AC re-synthesis via score_gate_loop +
synthesize_for_feature, then re-score.

Bounded to ONE re-synthesis per feature per process (module-level set) so a
feature that still cannot reach 0.85 after re-synthesis is left blocked without
re-spinning — no livelock.

Public API:
- ``score_gate_loop`` — re-exported from bob3.spec_synthesizer; the retry loop
  that regenerates ACs until composite >= threshold.
- ``synthesize_for_feature`` — re-exported from bob3.spec_synthesizer; the async
  synthesizer callable that calls out to the LLM.
- ``resynthesize_gate_blocked_feature`` — single entry point for mid-run
  re-synthesis of a gate-blocked feature, bounded to ONE attempt per feature.
- ``is_resynthesis_attempted`` — idempotency predicate.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from bob3.spec_synthesizer import (
    score_gate_loop,  # noqa: F401 — re-exported as AC entry point
    synthesize_for_feature,  # noqa: F401 — re-exported as AC entry point
)

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


def resynthesize_gate_blocked_feature(
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
        return None, 0.0

    _mark_attempted(feature_id)

    try:
        if synthesize_fn is None:
            synthesize_fn = synthesize_for_feature
        if score_gate_fn is None:
            score_gate_fn = score_gate_loop
    except Exception as exc:
        logger.warning("gate_blocked_resynthesis: synthesizer import failed: %s", exc)
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
            "gate_blocked_resynthesis: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0


__all__ = [
    "score_gate_loop",
    "synthesize_for_feature",
    "resynthesize_gate_blocked_feature",
    "is_resynthesis_attempted",
]
