"""Gate-blocked feature re-synthesis facade.

Exposes ``re_synthesize_acceptance_criteria`` — the named entry point for
regenerating a gate-blocked feature's acceptance criteria until they clear the
spec-quality gate. The implementation is :func:`bob3.spec_synthesizer.score_gate_loop`;
this module gives it the canonical name that the orchestrator's mid-run
re-synthesis path and the corresponding AC reference.

Also exposes ``resynthesize_gate_blocked_features`` (promotion-sweep entry point)
and ``is_already_resynthesized`` (idempotency predicate), both delegating to
:mod:`bob3.gate_resynth` so the orchestrator has a single, stable import point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_synthesizer import (
    score_gate_loop as _score_gate_loop,
    synthesize_for_feature as _synthesize_for_feature,
    resilient_import_scorer as _resilient_import_scorer,
)


async def re_synthesize_acceptance_criteria(
    *,
    title: str,
    description: str,
    project_id: str,
    threshold: float | None = None,
    workspace: "Path | None" = None,
    synthesize_fn: Any = None,
) -> Any:
    """Regenerate a gate-blocked feature's ACs until they clear the gate.

    Delegates to :func:`bob3.spec_synthesizer.score_gate_loop`, defaulting the
    synthesizer to :func:`synthesize_for_feature`. Returns the ScoreGateReport
    (``.criteria``, ``.composite``, ``.gate_passed``).
    """
    return await _score_gate_loop(
        synthesize_fn=synthesize_fn or _synthesize_for_feature,
        title=title,
        description=description,
        project_id=project_id,
        threshold=threshold,
        workspace=workspace,
    )


def resynthesize_gate_blocked_features(
    feature_id: str,
    name: str,
    description: str,
    project_id: str,
    workspace: "Path | None" = None,
    synthesize_fn: Any = None,
    score_gate_fn: Any = None,
) -> "tuple[list[str] | None, float]":
    """Attempt exactly one AC re-synthesis for a gate-blocked feature.

    Promotion-sweep entry point. Bounded to ONE attempt per feature per process
    via the module-level set in :mod:`bob3.gate_resynth` — prevents the livelock
    where gate-blocked features loop the blocked→test-writer→CodeT cycle forever.

    Delegates to :func:`bob3.gate_resynth.resynthesize_gate_blocked_feature`.

    Args:
        feature_id: Unique identifier of the gate-blocked feature.
        name: Feature name/title for the synthesizer prompt.
        description: Feature description for the synthesizer prompt.
        project_id: Project identifier passed to the synthesizer.
        workspace: Optional workspace path passed to the synthesizer.
        synthesize_fn: Override synthesizer callable (for testing).
        score_gate_fn: Override score-gate loop callable (for testing).

    Returns:
        ``(new_acs, new_composite)`` if re-synthesis produced criteria, else
        ``(None, 0.0)``.

    Raises:
        ValueError: If feature_id or project_id are not non-empty strings.
    """
    from bob3.gate_resynth import resynthesize_gate_blocked_feature as _resynth  # noqa: PLC0415
    return _resynth(
        feature_id=feature_id,
        name=name,
        description=description,
        project_id=project_id,
        workspace=workspace,
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )


# Alias required by AC: "Function defined: bob3.score_gate_loop.resynthesizegate_blocked_features"
resynthesizegate_blocked_features = resynthesize_gate_blocked_features


def robust_import_scorer():
    """Import the spec-quality scorer robustly, regardless of process cwd.

    This is the canonical entry point for resilient scorer import in the
    score_gate_loop module. Delegates to
    :func:`bob3.spec_synthesizer.resilient_import_scorer`.

    Behaviour contract:
    - Attempt the import directly first (fast path, cwd=<gen>).
    - On ModuleNotFoundError, derive the gen root from the module's __file__
      path and add it to sys.path, then retry.
    - If still not found after the path-augmented retry, raise ImportError
      loudly — infrastructure errors MUST NOT be swallowed into a silent
      per-feature deterministic fallback.

    Returns a callable ``compute(name, description, acceptance_criteria)``
    that produces an object with ``.composite`` and ``.rationale`` attributes.

    Raises:
        ImportError: If the scorer cannot be found even after adding the gen
            root to sys.path. This is always a hard environment error.
    """
    return _resilient_import_scorer()


def is_already_resynthesized(feature_id: str) -> bool:
    """Return True if a re-synthesis has already been attempted for this feature.

    Idempotency predicate — used by the orchestrator's promotion sweep to skip
    features that have already had one re-synthesis attempt this process lifetime,
    preventing the livelock without requiring the caller to track state itself.

    Delegates to :func:`bob3.gate_resynth.is_synthesis_attempted`.

    Args:
        feature_id: The feature's unique identifier string.

    Returns:
        True when a re-synthesis attempt has been recorded for *feature_id*,
        False otherwise (including when *feature_id* is empty or not a str).
    """
    from bob3.gate_resynth import is_synthesis_attempted as _is_attempted  # noqa: PLC0415
    return _is_attempted(feature_id)
