"""RCA-layer infra-error recovery — second-line defense against false NH.

Feature F-R7-479: when the orchestrator is about to mark a feature
``needs_human``, this module provides the second-line defense by inspecting
the entire history of failed attempts and answering: were ALL failures
infra-caused?

If the RCA verdict is ``infra_only``, the feature is reset to ``ready`` with
``refinement_attempts=0`` and any novel infra signature is auto-appended to
``config/spawn_retry.yaml``. The system learns the new transient pattern
WITHOUT a human edit.

The first line of defense (F-R7-478) is the spawn-layer regex guard in
``bob3.orchestrator.spawn_retry``. This module acts AFTER the spawn layer
fails: it catches novel infra signatures that slipped past the first-line
regex set.

Source directive: 2026-05-24 user — "claude cli having a bad day just retry
it, do not count it as needs human".
"""

from __future__ import annotations

import os
from typing import Callable

from bob3.orchestrator.rca_infra_recovery import (
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)

__all__ = [
    "auto_reset_if_infra",
    "classify_attempts",
    "harvest_novel_pattern",
    "rca_layer_infra_error_recovery_second_line_defense_against",
]


def rca_layer_infra_error_recovery_second_line_defense_against(
    feature_id: str,
    project_id: str,
    db_update_fn: Callable[..., None],
    workspace: str | os.PathLike[str] | None = None,
    failed_acs: list[str] | None = None,
    refinement_attempts: int | None = None,
) -> bool:
    """Second-line defense: RCA-layer infra-error recovery before NH transition.

    Called by the orchestrator BEFORE transitioning a feature to
    ``needs_human``. Delegates to ``auto_reset_if_infra``, which implements
    two recovery paths:

    1. **Infra-only** (this feature's core path): all failed attempts were
       infrastructure-caused → reset to ``ready`` with
       ``refinement_attempts=0`` and auto-append any novel error signature to
       ``config/spawn_retry.yaml``. The system self-heals without a human
       edit.

    2. **Code-emission defect**: verification gate failed on behavior/pytest
       ACs and ``refinement_attempts < 5`` → grant a fresh attempt.

    Parameters
    ----------
    feature_id:
        UUID of the feature being evaluated.
    project_id:
        Project UUID (passed through to audit events).
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
        Matches the signature of ``bob3.db.update_feature``.
    workspace:
        Path to the feature workspace directory. Used to locate agent logs
        and progress.jsonl. Defaults to the current directory.
    failed_acs:
        Acceptance-criteria strings (or error messages) that caused the
        verification gate to fail. Enables the code-emission-defect recovery
        path when provided alongside ``refinement_attempts``.
    refinement_attempts:
        Current refinement attempt count. Required for the
        code-emission-defect path's attempt cap (5 retries maximum).

    Returns
    -------
    True
        A recovery action was taken; the caller must NOT transition the
        feature to ``needs_human``.
    False
        No recovery is warranted; the feature should proceed to
        ``needs_human``.
    """
    return auto_reset_if_infra(
        feature_id=feature_id,
        project_id=project_id,
        db_update_fn=db_update_fn,
        workspace=workspace,
        failed_acs=failed_acs,
        refinement_attempts=refinement_attempts,
    )
