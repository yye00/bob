"""RCA sub-agent module: inspect attempt history and classify infra-only failures.

F-R7-479: second-line defense against false NH escalation. Before the orchestrator
transitions a feature to ``needs_human``, this module provides the classification
logic that answers: were ALL N attempts infrastructure-caused?

Public API:
- ``analyze_attempt_history``: classify a feature's entire failure history
- ``is_infra_only``: predicate that returns True when verdict is infra_only
"""

from __future__ import annotations

import os
from typing import Literal

import bob.orchestrator.rca_infra_recovery as _rca_recovery
from bob.orchestrator.rca_infra_recovery import (
    Verdict,
    harvest_novel_pattern,
    auto_reset_if_infra,
)

__all__ = [
    "analyze_attempt_history",
    "is_infra_only",
    "Verdict",
]


def analyze_attempt_history(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> Verdict:
    """Inspect the history of failed attempts for a feature.

    Delegates to the RCA infra recovery layer's ``classify_attempts``, which
    applies multi-signal heuristics (stderr pattern matching, work-event
    detection, cross-feature crash clustering) to determine whether ALL failures
    were infrastructure-caused.

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
        All failures appear to be infrastructure-caused (e.g. network error,
        rate limit, spawn failure). The feature should be reset to ``ready``.
    ``"feature_defect"``
        At least one failure has evidence of real work plus a non-infra error.
        The feature should proceed to ``needs_human``.
    ``"mixed"``
        Mix of infra and non-infra failures. Treat as ``feature_defect``.

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

    return _rca_recovery.classify_attempts(feature_id, workspace=workspace)


def is_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when all known failure attempts were infrastructure-caused.

    Convenience predicate wrapper around ``analyze_attempt_history``. Use this
    when only a boolean decision is needed (e.g. "should we auto-reset?").

    Parameters
    ----------
    feature_id:
        UUID of the feature to evaluate.
    workspace:
        Path to the feature workspace directory. Defaults to the current directory.

    Returns
    -------
    True
        All failures were infra-caused; feature may be auto-reset to ``ready``.
    False
        At least one failure was not infra-caused; do not auto-reset.

    Raises
    ------
    ValueError
        If ``feature_id`` is empty or None.
    TypeError
        If ``feature_id`` is not a string.
    """
    verdict = analyze_attempt_history(feature_id, workspace=workspace)
    return verdict == "infra_only"
