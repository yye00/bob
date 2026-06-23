"""Gate-blocked feature re-synthesis module (F-R7-632).

Provides functions to re-synthesize acceptance criteria for gate-blocked
features and track whether synthesis has already been attempted, preventing
the bob70 livelock where gate-blocked features loop endlessly.

Root cause of the livelock: when a feature fails the spec_quality gate
(composite < 0.85) it stays 'pending'. The run loop previously re-dispatched
it to test-writer/CodeT, which rebuild CODE. But spec_quality score depends on
the ACCEPTANCE CRITERIA, not the code — rebuilding code can never raise the
score. This module provides the correct recovery: re-synthesize the ACs once.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# In-memory set tracking which feature IDs have already had synthesis attempted.
# Using a module-level set to ensure one attempt per feature per process.
_synthesis_attempted: set[str] = set()


def mark_synthesis_attempted(feature_id: str) -> None:
    """Mark a feature as having had synthesis attempted.

    After calling this, ``re_synthesize_gate_blocked_feature`` will return
    (None, 0.0) for this feature_id without re-running the synthesizer.
    This prevents the bob70 livelock (658 "stays at pending" re-scores).

    Args:
        feature_id: The feature's unique identifier string.

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a str, got {type(feature_id).__name__!r}")
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    _synthesis_attempted.add(feature_id)


def re_synthesize_gate_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: Path | None = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> tuple[list[str] | None, float]:
    """Regenerate a gate-blocked feature's ACs via the score-gate synthesizer.

    Bounded to one re-synthesis per feature per process via the module-level
    ``_synthesis_attempted`` set. If this feature has already been attempted,
    returns (None, 0.0) immediately without re-running the synthesizer.

    The promotion sweep is synchronous, so this runs the async synthesizer in
    a private event loop (``asyncio.new_event_loop``).

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
        ValueError: If feature_id, name, or project_id are not non-empty strings.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a str, got {type(feature_id).__name__!r}")
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    if not isinstance(name, str):
        raise ValueError(f"name must be a str, got {type(name).__name__!r}")
    if not isinstance(project_id, str):
        raise ValueError(f"project_id must be a str, got {type(project_id).__name__!r}")
    if not project_id:
        raise ValueError("project_id must be non-empty")

    if feature_id in _synthesis_attempted:
        return None, 0.0

    mark_synthesis_attempted(feature_id)

    try:
        if synthesize_fn is None or score_gate_fn is None:
            from bob3.spec_synthesizer import (
                score_gate_loop as _score_gate_loop,
                synthesize_for_feature as _synthesize_for_feature,
            )
            if synthesize_fn is None:
                synthesize_fn = _synthesize_for_feature
            if score_gate_fn is None:
                score_gate_fn = _score_gate_loop
    except Exception as exc:
        logger.warning("gate_blocker: import of synthesizer failed: %s", exc)
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
            "gate_blocker: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0
