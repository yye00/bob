"""RCA-layer infra-error recovery — second-line defense against false NH.

F-R7-479: when the orchestrator is about to mark a feature ``needs_human``,
this module provides the second-line defense by inspecting the history of
failed attempts and answering: were ALL failures infra-caused?

If the RCA verdict is ``infra_only``, the feature is reset to ``ready`` with
``refinement_attempts=0`` and any novel infra error signature is auto-appended
to ``config/spawn_retry.yaml``. The system self-heals WITHOUT a human edit.

Source directive: "claude cli having a bad day just retry it, do not count it
as needs human."
"""

from __future__ import annotations

import os

import bob3.orchestrator.rca_infra_recovery as _rca
from bob3.orchestrator.rca_infra_recovery import (
    _append_discovered_pattern,
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)

__all__ = [
    "analyze_infra_failures",
    "append_transient_signature",
    "is_infra_only",
    "learn_signature",
    "auto_reset_if_infra",
    "classify_attempts",
    "harvest_novel_pattern",
]


def is_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when all known failure attempts were infrastructure-caused.

    Second-line defense predicate: called by the orchestrator BEFORE transitioning
    a feature to ``needs_human``. When True, the feature should be auto-reset to
    ``ready`` rather than escalated to a human.

    Classification is delegated to ``classify_attempts``, which applies
    multi-signal heuristics:
    - stderr tail pattern matching against known infra signatures
    - detection of whether real work events exist in progress.jsonl
    - cross-feature crash clustering within a 30-minute window
    - agent log size heuristics (tiny logs → pure spawn-time failures)

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Used to locate agent logs
        and progress.jsonl. Defaults to the current directory.

    Returns
    -------
    True
        All failures were infrastructure-caused; feature may be auto-reset.
    False
        At least one failure has real-work evidence or a non-infra error.

    Raises
    ------
    ValueError
        If ``feature_id`` is None, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a string.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")

    verdict = _rca.classify_attempts(feature_id, workspace=workspace)
    return verdict == "infra_only"


def learn_signature(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel infra error signature to ``config/spawn_retry.yaml``.

    When the RCA layer discovers a new error pattern that slipped past the
    first-line spawn-layer guard (F-R7-478), this function persists it so the
    first-line guard catches it on future runs. The system self-heals WITHOUT
    a human edit.

    Duplicate patterns are silently ignored (idempotent operation).

    Parameters
    ----------
    pattern:
        Regex string (or literal substring) identifying the novel infrastructure
        error signature. Must be non-empty.
    feature_id:
        UUID of the feature that triggered the discovery. Stored as provenance
        metadata alongside the pattern entry.

    Raises
    ------
    ValueError
        If ``pattern`` is None, empty, or whitespace-only, or if ``feature_id``
        is None, empty, or whitespace-only.
    TypeError
        If ``pattern`` or ``feature_id`` is not a string.
    """
    if pattern is None:
        raise ValueError("pattern must not be None")
    if not isinstance(pattern, str):
        raise TypeError(f"pattern must be a str, got {type(pattern).__name__}")
    if not pattern.strip():
        raise ValueError("pattern must not be empty or whitespace")

    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")

    _append_discovered_pattern(pattern, feature_id)


def analyze_infra_failures(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Inspect failed attempt history and classify whether all failures were infra-caused.

    Second-line defense (F-R7-479): called BEFORE the orchestrator transitions a
    feature to ``needs_human``. Applies multi-signal heuristics — stderr pattern
    matching, work-event detection, cross-feature crash clustering — to classify
    the failure root cause.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose attempt history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to the current directory.

    Returns
    -------
    ``"infra_only"``
        All failures were infrastructure-caused; feature may be auto-reset to
        ``ready`` with ``refinement_attempts=0``.
    ``"feature_defect"``
        At least one failure has real-work evidence or a non-infra error. The
        feature should proceed to ``needs_human``.
    ``"mixed"``
        Mix of infra and non-infra failures. Treat as ``feature_defect``.

    Raises
    ------
    ValueError
        If ``feature_id`` is None, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a string.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")

    return _rca.classify_attempts(feature_id, workspace=workspace)


def append_transient_signature(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel transient infra error signature to ``config/spawn_retry.yaml``.

    When the RCA layer discovers a new error pattern that slipped past the
    first-line spawn-layer guard (F-R7-478), this function persists it so the
    first-line guard catches it on future runs. The system self-heals WITHOUT
    a human edit.

    Duplicate patterns are silently ignored (idempotent operation).

    Parameters
    ----------
    pattern:
        Regex string (or literal substring) identifying the novel transient
        infrastructure error signature. Must be non-empty.
    feature_id:
        UUID of the feature that triggered the discovery. Stored as provenance
        metadata alongside the pattern entry.

    Raises
    ------
    ValueError
        If ``pattern`` is None, empty, or whitespace-only, or if ``feature_id``
        is None, empty, or whitespace-only.
    TypeError
        If ``pattern`` or ``feature_id`` is not a string.
    """
    if pattern is None:
        raise ValueError("pattern must not be None")
    if not isinstance(pattern, str):
        raise TypeError(f"pattern must be a str, got {type(pattern).__name__}")
    if not pattern.strip():
        raise ValueError("pattern must not be empty or whitespace")

    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")

    _append_discovered_pattern(pattern, feature_id)
