"""RCA-layer infra-error recovery — second-line defense against false NH.

F-R7-479: when the orchestrator is about to transition a feature to
``needs_human``, this module provides the second-line inspection that answers:
were ALL N failed attempts infrastructure-caused?

If the verdict is ``infra_only``, the feature is reset to ``ready`` with
``refinement_attempts=0`` and the discovered novel signature is auto-appended
to ``config/spawn_retry.yaml`` so the first-line guard (F-R7-478) catches it
on subsequent runs.

Public API
----------
- ``analyze_infra_errors``: classify the full attempt history for a feature
- ``is_infra_only``: boolean predicate — True when all failures were infra
- ``append_spawn_retry_signature``: persist a novel error signature to config
"""

from __future__ import annotations

import os

import bob3.orchestrator.rca_infra_recovery as _rca
from bob3.orchestrator.rca_infra_recovery import (
    Verdict,
    _append_discovered_pattern,
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)

__all__ = [
    "analyze_infra_errors",
    "analyze_infra_failures",
    "analyze_failure_history",
    "is_infra_only",
    "is_infra_only_verdict",
    "append_spawn_retry_signature",
    "append_signature_to_retry_config",
    "auto_reset_if_infra",
    "classify_attempts",
    "harvest_novel_pattern",
    "Verdict",
]


def analyze_infra_errors(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> Verdict:
    """Classify the failure history of a feature.

    Inspects agent logs, progress.jsonl, and cross-feature crash clustering to
    determine whether ALL failed attempts were infrastructure-caused.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose attempt history should be inspected.
    workspace:
        Path to the feature workspace directory. Used to locate agent logs and
        progress.jsonl. Defaults to the current directory.

    Returns
    -------
    ``"infra_only"``
        All failures appear infrastructure-caused. The feature should be reset
        to ``ready`` rather than escalated to a human.
    ``"feature_defect"``
        At least one failure has real-work evidence with a non-infra error.
        Escalate to ``needs_human``.
    ``"mixed"``
        Mix of infra and non-infra failures. Treat as ``feature_defect``.

    Raises
    ------
    ValueError
        If ``feature_id`` is ``None``, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a ``str``.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")

    return _rca.classify_attempts(feature_id, workspace=workspace)


def is_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return ``True`` when all failure attempts were infrastructure-caused.

    Convenience boolean predicate over ``analyze_infra_errors``. Use when only
    a go/no-go decision is needed (e.g. "should we auto-reset this feature?").

    Parameters
    ----------
    feature_id:
        UUID of the feature to evaluate.
    workspace:
        Path to the feature workspace directory. Defaults to the current directory.

    Returns
    -------
    True
        All failures were infra-caused; the feature may be auto-reset to ``ready``.
    False
        At least one failure was not infra-caused; do not auto-reset.

    Raises
    ------
    ValueError
        If ``feature_id`` is ``None``, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a ``str``.
    """
    verdict = analyze_infra_errors(feature_id, workspace=workspace)
    return verdict == "infra_only"


def append_spawn_retry_signature(
    pattern: str,
    feature_id: str,
) -> None:
    """Persist a novel infra error signature to ``config/spawn_retry.yaml``.

    When the RCA layer discovers an error pattern that slipped past the
    first-line spawn-layer guard (F-R7-478), this function appends it as a
    medium-confidence discovered pattern. On subsequent runs the first-line
    guard will match it automatically — the system self-heals WITHOUT a human
    edit.

    Duplicate patterns are silently ignored (idempotent).

    Parameters
    ----------
    pattern:
        Regex string (or literal substring) identifying the novel infra error.
        Must be a non-empty string.
    feature_id:
        UUID of the feature that triggered the discovery. Stored as provenance
        metadata alongside the pattern entry.

    Raises
    ------
    ValueError
        If ``pattern`` or ``feature_id`` is ``None``, empty, or whitespace-only.
    TypeError
        If ``pattern`` or ``feature_id`` is not a ``str``.
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


def analyze_failure_history(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> Verdict:
    """Alias for ``analyze_infra_errors`` — satisfies AC naming requirement."""
    return analyze_infra_errors(feature_id, workspace=workspace)


def is_infra_only_verdict(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Alias for ``is_infra_only`` — satisfies AC naming requirement."""
    return is_infra_only(feature_id, workspace=workspace)


def analyze_infra_failures(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> Verdict:
    """Alias for ``analyze_infra_errors`` — satisfies AC function-name requirement."""
    return analyze_infra_errors(feature_id, workspace=workspace)


def append_signature_to_retry_config(
    pattern: str,
    feature_id: str,
) -> None:
    """Alias for ``append_spawn_retry_signature`` — satisfies AC function-name requirement."""
    return append_spawn_retry_signature(pattern, feature_id)
