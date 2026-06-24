"""RCA-layer infra-error verdict — second-line defense against false NH (F-R7-479).

Before the orchestrator transitions a feature to ``needs_human``, this module
provides the second-line RCA inspection that answers: were ALL N failed attempts
infrastructure-caused?

If the verdict is ``infra_only``, the feature is reset to ``ready`` with
``refinement_attempts=0`` and the discovered novel signature is auto-appended to
``config/spawn_retry.yaml`` so the first-line guard (F-R7-478) catches it on
subsequent runs.

Public API
----------
- ``assess_infra_only``: return True when all failures were infrastructure-caused
- ``append_novel_signature``: persist a novel error pattern to spawn_retry.yaml
"""

from __future__ import annotations

import os
from typing import Literal

import bob.orchestrator.rca_infra_recovery as _rca_recovery
from bob.orchestrator.rca_infra_recovery import (
    Verdict,
    auto_reset_if_infra,
    harvest_novel_pattern,
)

__all__ = [
    "assess_infra_only",
    "append_novel_signature",
    "auto_reset_if_infra",
    "classify_attempts",
    "harvest_novel_pattern",
    "Verdict",
]


def classify_attempts(
    feature_id: str,
    workspace=None,
) -> Verdict:
    """Proxy to ``_rca_recovery.classify_attempts`` for patchability."""
    return _rca_recovery.classify_attempts(feature_id, workspace=workspace)


def assess_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when all failure attempts for a feature were infrastructure-caused.

    This is the second-line defense predicate called BEFORE the orchestrator
    transitions a feature to ``needs_human``. When True, the feature should be
    auto-reset to ``ready`` rather than escalated to a human.

    Classification delegates to ``classify_attempts``, which applies
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

    import sys as _sys
    _self = _sys.modules[__name__]
    _fn = getattr(_self, "classify_attempts")
    verdict: Verdict = _fn(feature_id, workspace=workspace)
    return verdict == "infra_only"


def append_novel_signature(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel infra error signature to ``config/spawn_retry.yaml``.

    When the RCA layer discovers a new error pattern that slipped past the
    first-line spawn-layer guard (F-R7-478), this function persists it as a
    medium-confidence discovered pattern. On subsequent runs, the first-line
    guard will match and handle it automatically — the system self-heals
    WITHOUT a human edit.

    Duplicate patterns are silently ignored (idempotent operation).

    Parameters
    ----------
    pattern:
        Regex string (or literal substring) that identifies the novel
        infrastructure error signature. Must be non-empty.
    feature_id:
        UUID of the feature that triggered the discovery. Stored as provenance
        metadata alongside the pattern entry.

    Raises
    ------
    ValueError
        If ``pattern`` is None, empty, or whitespace-only, or if
        ``feature_id`` is None, empty, or whitespace-only.
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

    _rca_recovery._append_discovered_pattern(pattern, feature_id)
