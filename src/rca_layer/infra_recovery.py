"""RCA-layer infra-error recovery — thin public wrapper satisfying F-R7-479 ACs.

Provides ``check_infra_only_verdict`` as the canonical function name required by
the acceptance criterion: ``rca_layer.infra_recovery.check_infra_only_verdict``.

Delegates all logic to ``bob3.orchestrator.rca_infra_recovery`` so there is a
single authoritative implementation.
"""

from __future__ import annotations

import os
from typing import Any

import bob3.orchestrator.rca_infra_recovery as _rca_mod
from bob3.orchestrator.rca_infra_recovery import (
    Verdict,
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)

__all__ = [
    "check_infra_only_verdict",
    "analyze_infra_only_failures",
    "reset_feature_to_ready",
    "auto_reset_if_infra",
    "classify_attempts",
    "harvest_novel_pattern",
    "Verdict",
]


def check_infra_only_verdict(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when all failed attempts for a feature were infra-caused.

    Inspects the attempt history via the multi-signal heuristic classifier in
    ``bob3.orchestrator.rca_infra_recovery`` and returns True only when the
    verdict is ``"infra_only"``.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose attempt history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to the current
        directory.

    Returns
    -------
    True
        All failures were infra-caused; the feature may be auto-reset to
        ``ready``.
    False
        At least one failure was NOT infra-caused; do not auto-reset.

    Raises
    ------
    ValueError
        If ``feature_id`` is empty or None.
    TypeError
        If ``feature_id`` is not a string.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty")

    verdict: Verdict = _rca_mod.classify_attempts(feature_id, workspace=workspace)
    return verdict == "infra_only"


def analyze_infra_only_failures(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when ALL failed attempts for a feature were infra-caused.

    This is the second-line RCA defense (F-R7-479). Inspects the attempt
    history via multi-signal heuristics and returns True only when the
    verdict is ``"infra_only"``, indicating the feature should be reset to
    ``ready`` rather than escalated to ``needs_human``.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose attempt history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to the current
        directory.

    Returns
    -------
    True
        All failures were infra-caused; the feature may be auto-reset.
    False
        At least one failure was NOT infra-caused.

    Raises
    ------
    ValueError
        If ``feature_id`` is empty or None.
    TypeError
        If ``feature_id`` is not a string.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty")

    verdict: Verdict = _rca_mod.classify_attempts(feature_id, workspace=workspace)
    return verdict == "infra_only"


def reset_feature_to_ready(
    feature_id: str,
    db_update_fn: Any,
    refinement_attempts: int = 0,
) -> None:
    """Reset a feature to ``ready`` state after an infra-only RCA verdict.

    When the RCA layer determines that all failures were infrastructure-caused,
    this function transitions the feature back to ``ready`` with
    ``refinement_attempts=0`` so the orchestrator can retry without human
    intervention.

    Parameters
    ----------
    feature_id:
        UUID of the feature to reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
        Matches the signature of ``bob3.db.update_feature``.
    refinement_attempts:
        Value to set for ``refinement_attempts``. Defaults to 0 (fresh budget).

    Raises
    ------
    ValueError
        If ``feature_id`` is empty or None, or if ``refinement_attempts < 0``.
    TypeError
        If ``feature_id`` is not a string, ``db_update_fn`` is not callable,
        or ``refinement_attempts`` is not an int.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty")
    if not callable(db_update_fn):
        raise TypeError(f"db_update_fn must be callable, got {type(db_update_fn).__name__}")
    if not isinstance(refinement_attempts, int):
        raise TypeError(
            f"refinement_attempts must be an int, got {type(refinement_attempts).__name__}"
        )
    if refinement_attempts < 0:
        raise ValueError(f"refinement_attempts must be >= 0, got {refinement_attempts}")

    db_update_fn(feature_id, status="ready", refinement_attempts=refinement_attempts)
