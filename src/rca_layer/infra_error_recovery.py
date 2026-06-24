"""RCA-layer infra-error recovery — second-line defense against false NH.

F-R7-479: before the orchestrator transitions a feature to ``needs_human``,
this module provides the second line of defense by inspecting the history of
failed attempts and answering: were ALL N attempts infrastructure-caused?

If the verdict is ``infra_only``, the feature is reset to ``ready`` with
``refinement_attempts=0`` and any novel infra signature is auto-appended to
``config/spawn_retry.yaml`` so the first-line spawn-layer guard (F-R7-478)
catches it in future runs. The system learns the new transient pattern WITHOUT
a human edit.

Source directive: 2026-05-24 user — "claude cli having a bad day just retry
it, do not count it as needs human".

Public API
----------
diagnose_infra_only(feature_id, workspace=None) -> Verdict
    Inspect attempt history and return raw verdict ("infra_only", "feature_defect", "mixed").

verdict_infra_only(feature_id, workspace=None) -> bool
    Return True when all failure attempts were infra-caused (infra_only verdict).

append_novel_signature(pattern, feature_id) -> None
    Append a novel infra error signature to config/spawn_retry.yaml.
"""

from __future__ import annotations

import os

import bob.orchestrator.rca_infra_recovery as _rca_mod
from bob.orchestrator.rca_infra_recovery import (
    Verdict,
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)
from bob.orchestrator.rca_infra_recovery import _append_discovered_pattern as _append_pattern

__all__ = [
    "diagnose_infra_only",
    "verdict_infra_only",
    "append_novel_signature",
    "Verdict",
    "classify_attempts",
    "harvest_novel_pattern",
    "auto_reset_if_infra",
]


def diagnose_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> Verdict:
    """Diagnose whether all failed attempts for a feature were infra-caused.

    This is the primary RCA entry point called by the orchestrator BEFORE
    transitioning a feature to ``needs_human``. It runs the multi-signal
    heuristic classifier and returns the raw verdict.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose attempt history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to the current
        directory.

    Returns
    -------
    ``"infra_only"``
        All failures appear infrastructure-caused; the feature should be
        auto-reset to ``ready`` with ``refinement_attempts=0``.
    ``"feature_defect"``
        At least one failure has evidence of real work plus a non-infra error;
        proceed to ``needs_human``.
    ``"mixed"``
        Mix of infra and non-infra failures; treat as ``feature_defect``.

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

    return _rca_mod.classify_attempts(feature_id, workspace=workspace)


def verdict_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when all failed attempts for a feature were infra-caused.

    Calls the multi-signal heuristic classifier in
    ``bob.orchestrator.rca_infra_recovery`` and returns True only when the
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


def append_novel_signature(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel infra error signature to config/spawn_retry.yaml.

    When the RCA layer discovers an error pattern that is not yet in the
    first-line spawn-layer regex set (F-R7-478), this function records it
    so that future spawns catch it automatically without a human edit.

    The entry is written under ``discovered_patterns`` with
    ``confidence: medium``. A subsequent pattern-graduation pass promotes
    it to ``high`` once a matching spawn succeeds.

    Duplicate patterns (same ``pattern`` string) are silently skipped.

    Parameters
    ----------
    pattern:
        Regex or substring pattern that identifies the novel infra error.
    feature_id:
        UUID of the feature where this pattern was first observed. Stored
        as provenance metadata in the YAML entry.

    Raises
    ------
    ValueError
        If ``pattern`` or ``feature_id`` is empty or None.
    TypeError
        If ``pattern`` or ``feature_id`` is not a string.
    """
    if pattern is None:
        raise ValueError("pattern must not be None")
    if not isinstance(pattern, str):
        raise TypeError(f"pattern must be a str, got {type(pattern).__name__}")
    if not pattern.strip():
        raise ValueError("pattern must not be empty")
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty")

    _rca_mod._append_discovered_pattern(pattern=pattern, feature_id=feature_id)
