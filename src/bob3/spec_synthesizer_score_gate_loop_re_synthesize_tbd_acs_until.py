"""Score-gate loop wrapper for the spec synthesizer (F-R7-615).

Exposes :func:`spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until`
as the canonical entry-point for re-synthesizing TBD acceptance criteria until
the composite spec_quality_score meets the configured threshold.

Architecture:
  - Delegates to :func:`bob3.spec_synthesizer.score_gate_loop` for the
    retry/scoring logic and :func:`bob3.spec_synthesizer.deterministic_fallback`
    for exhaustion fallback.
  - The score gate loop calls the supplied ``synthesize_fn`` (default:
    :func:`bob3.spec_synthesizer.synthesize_for_feature`) up to ``max_retries``
    times, passing ``retry_feedback`` on each retry so the LLM can correct
    the failing sub-metrics.
  - Returns a plain dict so callers don't need to import the dataclass.

Return dict keys:
  gate_passed        bool   — True if threshold was met within max_retries
  gate_failed        bool   — True if threshold was never met
  gate_avg_attempts  int    — number of synthesis attempts consumed
  criteria           list   — final acceptance criteria (may be fallback)
  composite          float  — composite quality score of final criteria
  rationale          list   — sub-metric hints from the scorer
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from bob3.spec_synthesizer import (
    ScoreGateReport,
    _DEFAULT_MAX_RETRIES,
    _DEFAULT_SPEC_QUALITY_THRESHOLD,
    score_gate_loop,
    score_gate_threshold_from_env,
    synthesize_for_feature,
)


async def spec_synthesizer_score_gate_loop_re_synthesize_tbd_acs_until(
    *,
    title: str,
    description: str,
    project_id: str,
    synthesize_fn: Callable[..., Awaitable[list[str] | None]] | None = None,
    threshold: float | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    use_fallback: bool = True,
    project_context: str = "",
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Re-synthesize TBD ACs until composite spec quality score meets threshold.

    Wraps :func:`~bob3.spec_synthesizer.score_gate_loop` to provide a
    self-contained entry-point that can be invoked from sanitize_spec_file,
    CLI commands, or tests without importing the internal dataclass.

    Parameters
    ----------
    title:
        Feature title used for slug derivation and prompt context.
    description:
        Feature description passed to the synthesizer.
    project_id:
        Bob3 project ID forwarded to the LLM sub-agent spawn call.
    synthesize_fn:
        Async callable with signature ``(*, project_id, title, description,
        project_context, workspace, retry_feedback) -> list[str] | None``.
        Defaults to :func:`~bob3.spec_synthesizer.synthesize_for_feature`.
    threshold:
        Composite score threshold [0, 1] that the ACs must reach.
        Defaults to ``BOB3_SPEC_QUALITY_THRESHOLD`` env var (0.85 if unset).
    max_retries:
        Maximum number of synthesis attempts before falling back.
    use_fallback:
        When True (default), use :func:`~bob3.spec_synthesizer.deterministic_fallback`
        on exhaustion rather than raising.
    project_context:
        Optional project-level context string forwarded to the synthesizer.
    workspace:
        Optional path to the project workspace root.

    Returns
    -------
    dict with keys:
        gate_passed (bool), gate_failed (bool), gate_avg_attempts (int),
        criteria (list[str] | None), composite (float), rationale (list[str])
    """
    if threshold is None:
        threshold = score_gate_threshold_from_env()

    if synthesize_fn is None:
        synthesize_fn = synthesize_for_feature

    report: ScoreGateReport = await score_gate_loop(
        synthesize_fn=synthesize_fn,
        title=title,
        description=description,
        project_id=project_id,
        threshold=threshold,
        max_retries=max_retries,
        use_fallback=use_fallback,
        project_context=project_context,
        workspace=workspace,
    )

    return {
        "gate_passed": report.gate_passed,
        "gate_failed": report.gate_failed,
        "gate_avg_attempts": report.gate_avg_attempts,
        "criteria": report.criteria,
        "composite": report.composite,
        "rationale": report.rationale,
    }
