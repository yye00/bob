"""Gate-blocked feature re-synthesis module (feature a61c0e92).

Fixes the livelock where gate-blocked features are endlessly re-dispatched
to the test-writer/CodeT cycle. The spec_quality score is a function of
ACCEPTANCE CRITERIA, not code — rebuilding code can never raise the score.

Fix: when the promotion sweep finds a gate-blocked feature, re-run the
score-gate synthesizer to regenerate ACs, then re-score. Bounded to ONE
re-synthesis per feature per process (module-level set) to prevent livelock.

Public API:
    re_synthesize_gate_blocked_feature(feature_id, name, description, project_id)
        — attempt one AC re-synthesis for a gate-blocked feature.
    is_already_resynthesized(feature_id)
        — idempotency predicate.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from bob3.research_strategies import validate_against_spec_quality_gate

logger = logging.getLogger(__name__)

# Module-level set: one re-synthesis attempt per feature per process.
# Prevents the livelock where gate-blocked features cycle forever.
_resynthesized: set[str] = set()


def is_already_resynthesized(feature_id: str) -> bool:
    """Return True if re-synthesis has already been attempted for this feature.

    Args:
        feature_id: The feature's unique identifier string.

    Returns:
        True when a re-synthesis attempt has been recorded for *feature_id*,
        False otherwise (including when *feature_id* is empty or not a str).
    """
    if not isinstance(feature_id, str) or not feature_id:
        return False
    return feature_id in _resynthesized


def re_synthesize_gate_blocked_feature(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: "Path | None" = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> "tuple[list[str] | None, float]":
    """Attempt exactly one AC re-synthesis for a gate-blocked feature.

    When the promotion sweep finds a feature blocked by the spec_quality gate
    (composite < 0.85), this function re-runs the score-gate synthesizer to
    regenerate its acceptance criteria, then re-scores. If the new ACs clear
    the gate, the caller should persist them and promote the feature.

    Bounded to ONE attempt per feature per process via the module-level
    ``_resynthesized`` set — prevents the livelock where gate-blocked features
    cycle the blocked→test-writer→CodeT path forever without the score rising.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
        name: Feature name/title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier passed to the synthesizer.
        workspace: Optional workspace path passed to the synthesizer.
        synthesize_fn: Override synthesizer callable (for testing).
        score_gate_fn: Override score-gate loop callable (for testing).

    Returns:
        ``(new_acs, new_composite)`` if re-synthesis produced criteria and
        the gate passed, otherwise ``(None, 0.0)``.

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

    if feature_id in _resynthesized:
        logger.debug(
            "gate_synthesizer: already attempted %s — skipping to prevent livelock",
            feature_id[:8],
        )
        return None, 0.0

    _resynthesized.add(feature_id)

    try:
        if synthesize_fn is None or score_gate_fn is None:
            from bob3.spec_synthesizer import (  # noqa: PLC0415
                score_gate_loop as _sgl,
                synthesize_for_feature as _sff,
            )
            if synthesize_fn is None:
                synthesize_fn = _sff
            if score_gate_fn is None:
                score_gate_fn = _sgl
    except Exception as exc:
        logger.warning("gate_synthesizer: import of synthesizer failed: %s", exc)
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
            gate_result = validate_against_spec_quality_gate(list(report.criteria))
            if not gate_result["passed"]:
                logger.warning(
                    "gate_synthesizer: re-synthesized ACs for %s failed canonical-form validation: %s",
                    feature_id[:8],
                    gate_result["non_canonical"],
                )
                return None, 0.0
            return report.criteria, float(report.composite or 0.0)
    except Exception as exc:
        logger.warning(
            "gate_synthesizer: mid-run re-synthesis failed for %s: %s",
            feature_id[:8] if len(feature_id) >= 8 else feature_id,
            exc,
            exc_info=True,
        )
    return None, 0.0
