"""Gate-blocked feature handler for bob72.

Exposes ``handle_gate_blocked_feature`` — the entry point that the orchestrator
calls when a feature fails the spec-quality gate (composite < 0.85).

Root cause of the bob70 livelock
---------------------------------
When a feature fails the spec_quality gate it stays 'pending'. The old
recovery dispatched it back to test-writer/CodeT which rebuild *code*. But
spec_quality is a function of the *acceptance criteria*, not the code — so
rebuilding code could never raise it. The feature looped the same
blocked→test-writer→CodeT cycle every ~30 min forever (bob70: 658 "stays
at pending" re-scores, 78% CPU, frozen DB).

Fix: when the promotion sweep finds a gate-blocked feature, call
``handle_gate_blocked_feature`` once. It re-runs the score-gate synthesizer to
regenerate the ACs. If the new ACs clear the gate, persist them and promote.
Bounded to ONE re-synthesis per feature per process (in-memory set) so a
feature that still can't reach 0.85 is left blocked without re-spinning.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from bob3.score_gate_loop import re_synthesize_acceptance_criteria
from bob3.spec_quality.quality_score import compute_score as _compute_score, gate_for_ready as _gate_for_ready

logger = logging.getLogger(__name__)


def run_spec_critic(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    workspace: "Path | None" = None,
    constitution_path: "Path | None" = None,
    findings_path: "Path | None" = None,
) -> dict:
    """Run the adversarial spec-critic before dispatching any implementer.

    Called by the orchestrator after spec extraction and before any implementer
    agent is dispatched. Uses :class:`bob74.spec_critic.SpecCritic` to load a
    versioned ``spec_constitution.md`` and emit per-feature structured defects.
    Findings persist to ``reviews/spec_findings.yaml`` keyed by spec hash.

    Parameters
    ----------
    feature_id:
        Unique identifier for the feature.
    name:
        Human-readable feature name.
    description:
        Full feature description text.
    acceptance_criteria:
        List of AC strings for this feature.
    workspace:
        Repository root directory override; mainly for testing.
    constitution_path:
        Override path to ``spec_constitution.md``; mainly for testing.
    findings_path:
        Override path to ``spec_findings.yaml``; mainly for testing.

    Returns
    -------
    dict with keys:
        gate_passed : bool — True when no defects (codegen may proceed)
        defects : list[dict] — structured defect records
        spec_hash : str — 16-char SHA-256 of the spec content
    """
    from bob74.spec_critic import SpecCritic  # noqa: PLC0415 — deferred to avoid circular

    critic = SpecCritic(
        workspace=workspace,
        constitution_path=constitution_path,
        findings_path=findings_path,
    )
    return critic.critique(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
    )

# In-memory bound: each feature ID may be re-synthesized at most once per process.
_resynthesized: set[str] = set()


def handle_gate_blocked_feature(
    feature_id: str,
    title: str,
    description: str,
    project_id: str,
    *,
    threshold: float | None = None,
    workspace: "Path | str | None" = None,
    synthesize_fn: Any = None,
) -> "tuple[list[str] | None, float]":
    """Attempt one AC re-synthesis for a gate-blocked feature.

    Called by the orchestrator's promotion sweep when a feature has
    spec_quality_score < 0.85.  Runs the async score-gate synthesizer
    synchronously in a fresh event loop, returns ``(new_acs, composite)``
    on success or ``(None, 0.0)`` if re-synthesis is skipped or fails.

    Bounds: each ``feature_id`` is re-synthesized at most once per process
    (tracked in the module-level ``_resynthesized`` set).  A feature that
    still can't reach the threshold after one attempt is left blocked —
    no further re-dispatch, no livelock.

    Parameters
    ----------
    feature_id:
        UUID of the gate-blocked feature.
    title:
        Feature name / title used by the synthesizer.
    description:
        Feature description used by the synthesizer.
    project_id:
        Bob3 project UUID, forwarded to the synthesizer.
    threshold:
        Optional override for the 0.85 gate threshold.
    workspace:
        Path to the workspace directory; forwarded to the synthesizer.
    synthesize_fn:
        Optional synthesizer override for testing.
    """
    if not feature_id:
        raise ValueError("feature_id must be a non-empty string")
    if not title:
        raise ValueError("title must be a non-empty string")

    if feature_id in _resynthesized:
        logger.debug("handle_gate_blocked_feature: already re-synthesized %s; skipping", feature_id[:8])
        return None, 0.0

    _resynthesized.add(feature_id)

    ws = Path(workspace) if workspace and not isinstance(workspace, Path) else workspace

    try:
        loop = asyncio.new_event_loop()
        try:
            report = loop.run_until_complete(
                re_synthesize_acceptance_criteria(
                    title=title,
                    description=description,
                    project_id=project_id,
                    threshold=threshold,
                    workspace=ws,
                    synthesize_fn=synthesize_fn,
                )
            )
        finally:
            loop.close()
    except Exception:
        logger.warning(
            "handle_gate_blocked_feature: re-synthesis raised for %s",
            feature_id[:8],
            exc_info=True,
        )
        return None, 0.0

    if report is None or not report.criteria:
        return None, 0.0

    return report.criteria, float(report.composite or 0.0)
