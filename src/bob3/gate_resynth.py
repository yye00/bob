"""Gate-blocked feature re-synthesis (F-R7-632).

When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The run loop's only recovery is to re-dispatch to test-writer/CodeT,
which rebuild CODE. But the spec_quality score depends on the ACCEPTANCE
CRITERIA, not the code — rebuilding code can never raise the score. This module
provides the correct recovery: attempt one AC re-synthesis via the score-gate
synthesizer, then re-score.

Bounded to ONE re-synthesis per feature per process (module-level set), so a
feature that still cannot reach 0.85 after re-synthesis is left blocked without
re-spinning — no livelock.

Public API:
- ``resynthesize_gate_blocked_feature(feature_id, name, description, project_id)``
  — called by the orchestrator's promotion sweep.
- ``is_synthesis_attempted(feature_id)`` — predicate for tests/orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level set: one re-synthesis attempt per feature per process.
_synthesis_attempted: set[str] = set()


def is_synthesis_attempted(feature_id: str) -> bool:
    """Return True if a re-synthesis has already been attempted for this feature."""
    if not isinstance(feature_id, str) or not feature_id:
        return False
    return feature_id in _synthesis_attempted


def _mark_attempted(feature_id: str) -> None:
    _synthesis_attempted.add(feature_id)


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

    If the feature has already been attempted, returns (None, 0.0) immediately
    without re-running the synthesizer — prevents livelock.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
        name: Feature name/title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier passed to the synthesizer.
        workspace: Optional workspace path passed to the synthesizer.
        synthesize_fn: Override synthesizer callable (for testing).
        score_gate_fn: Override score-gate loop callable (for testing).

    Returns:
        (new_acs, new_composite) if re-synthesis produced criteria, else
        (None, 0.0).

    Raises:
        ValueError: If feature_id, project_id are not non-empty strings.
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

    if feature_id in _synthesis_attempted:
        logger.debug(
            "gate_resynth: already attempted %s — skipping to prevent livelock",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
        )
        return None, 0.0

    _mark_attempted(feature_id)

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
        logger.warning("gate_resynth: import of synthesizer failed: %s", exc)
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
            "gate_resynth: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0
