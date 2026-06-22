"""RCA-layer infra-error recovery — public façade for F-R7-479.

This module provides the top-level public API for the second-line defense
against false needs_human (NH) escalation. Before the orchestrator transitions
a feature to ``needs_human``, these helpers can be called to determine whether
ALL failures were infrastructure-caused and to self-learn novel error signatures.

Two-layer architecture:
  - F-R7-478 (first line): spawn-layer regex guard ``bob3.orchestrator.spawn_retry``
  - F-R7-479 (second line, this module): RCA sub-agent inspection of attempt history

If the RCA verdict is ``infra_only``, the feature is reset to ``ready`` with
``refinement_attempts=0`` and the discovered novel signature is auto-appended to
``config/spawn_retry.yaml`` so the first-line guard catches it in future runs.

Source directive: 2026-05-24 user — "claude cli having a bad day just retry it,
do not count it as needs human".
"""

from __future__ import annotations

import os
from typing import Literal

from bob3.orchestrator.rca_infra_recovery import (
    Verdict,
    _all_infra_patterns,
    _append_discovered_pattern,
    _matches_infra_pattern,
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)

__all__ = [
    "is_infra_only_failure",
    "append_novel_signature",
    "analyze_infra_only",
    "reset_feature_with_learned_signature",
    "diagnose_infra_only",
    "reset_feature_on_infra_verdict",
    "reset_feature_on_infra_only",
    "append_signature_to_spawn_retry",
    "classify_attempts",
    "harvest_novel_pattern",
    "auto_reset_if_infra",
    "Verdict",
    "analyze_infra_causation",
    "reset_feature_from_infra_error",
]


def is_infra_only_failure(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when all known failure attempts were infrastructure-caused.

    This is the second-line defense predicate: it is called by the orchestrator
    BEFORE transitioning a feature to ``needs_human``. When True, the feature
    should be auto-reset to ``ready`` rather than escalated to a human.

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

    verdict: Verdict = classify_attempts(feature_id, workspace=workspace)
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

    _append_discovered_pattern(pattern, feature_id)


def analyze_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> "Verdict":
    """Analyze whether all failure attempts for a feature were infra-caused.

    This is the named entry-point required by F-R7-479's second-line defense.
    It delegates to ``classify_attempts`` and returns the full verdict string
    so callers can distinguish infra_only, feature_defect, and mixed.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    Verdict
        One of "infra_only", "feature_defect", or "mixed".

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

    return classify_attempts(feature_id, workspace=workspace)


def reset_feature_with_learned_signature(
    feature_id: str,
    db_update_fn,
    project_id: str = "",
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Reset a feature to ready and auto-learn any novel infra error signature.

    This is the named entry-point required by F-R7-479. It orchestrates the
    full second-line defense:

    1. Calls ``analyze_infra_only`` to determine whether all failures were
       infrastructure-caused.
    2. If ``infra_only``: harvests a novel pattern from the stderr tails,
       appends it to ``config/spawn_retry.yaml``, then resets the feature to
       ``ready`` with ``refinement_attempts=0``.
    3. If not ``infra_only``: returns False without touching the database.

    The system learns the new transient pattern WITHOUT a human edit, so the
    first-line spawn-layer guard (F-R7-478) catches it on future runs.

    Parameters
    ----------
    feature_id:
        UUID of the feature to potentially reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature in the DB.
    project_id:
        Project identifier (passed through to ``auto_reset_if_infra``).
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    True
        Feature was reset to ready (infra_only verdict confirmed).
    False
        Feature was NOT reset (non-infra failures detected).

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

    return auto_reset_if_infra(
        feature_id=feature_id,
        project_id=project_id,
        db_update_fn=db_update_fn,
        workspace=workspace,
    )


def diagnose_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> "Verdict":
    """Diagnose whether all failure attempts for a feature were infra-caused.

    Named entry-point required by AC: ``bob3.rca_infra_recovery.diagnose_infra_only``.
    Equivalent to ``analyze_infra_only`` — returns the full verdict string so
    callers can distinguish between ``infra_only``, ``feature_defect``, and
    ``mixed`` without performing a boolean test.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    Verdict
        One of ``"infra_only"``, ``"feature_defect"``, or ``"mixed"``.

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

    return classify_attempts(feature_id, workspace=workspace)


def reset_feature_on_infra_verdict(
    feature_id: str,
    db_update_fn,
    project_id: str = "",
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Reset a feature to ready when the RCA verdict is infra_only.

    Named entry-point required by AC: ``bob3.rca_infra_recovery.reset_feature_on_infra_verdict``.
    Equivalent to ``reset_feature_with_learned_signature`` — orchestrates the
    full second-line defense (F-R7-479):

    1. Diagnoses whether all failures were infrastructure-caused via
       ``diagnose_infra_only``.
    2. If ``infra_only``: harvests any novel pattern from stderr tails,
       appends it to ``config/spawn_retry.yaml``, then resets the feature to
       ``ready`` with ``refinement_attempts=0``.
    3. If not ``infra_only``: returns False without touching the database.

    Parameters
    ----------
    feature_id:
        UUID of the feature to potentially reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature in the DB.
    project_id:
        Project identifier (passed through to ``auto_reset_if_infra``).
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    True
        Feature was reset to ready (infra_only verdict confirmed).
    False
        Feature was NOT reset (non-infra failures detected).

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

    return auto_reset_if_infra(
        feature_id=feature_id,
        project_id=project_id,
        db_update_fn=db_update_fn,
        workspace=workspace,
    )


def append_signature_to_spawn_retry(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel infra error signature to ``config/spawn_retry.yaml``.

    Named entry-point required by AC: ``bob3.rca_infra_recovery.append_signature_to_spawn_retry``.
    Equivalent to ``append_novel_signature`` — persists a newly discovered
    transient error pattern as a medium-confidence entry so the first-line
    spawn-layer guard (F-R7-478) catches it on future runs WITHOUT a human edit.

    Duplicate patterns are silently ignored (idempotent operation).

    Parameters
    ----------
    pattern:
        Regex string (or literal substring) identifying the novel infra error
        signature. Must be non-empty.
    feature_id:
        UUID of the feature that triggered the discovery. Stored as provenance
        metadata alongside the pattern entry.

    Raises
    ------
    ValueError
        If ``pattern`` or ``feature_id`` is None, empty, or whitespace-only.
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


def analyze_infra_causation(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None" = None,
) -> "Verdict":
    """Analyze whether all failure attempts for a feature were infrastructure-caused.

    Named entry-point required by F-R7-479 AC: ``bob3.rca_infra_recovery.analyze_infra_causation``.
    Second-line defense predicate called BEFORE the orchestrator transitions a
    feature to ``needs_human``.

    Delegates to ``classify_attempts`` from the orchestrator layer and returns
    the full verdict so callers can distinguish ``infra_only``, ``feature_defect``,
    and ``mixed``.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    Verdict
        One of ``"infra_only"``, ``"feature_defect"``, or ``"mixed"``.

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

    return classify_attempts(feature_id, workspace=workspace)


def reset_feature_from_infra_error(
    feature_id: str,
    db_update_fn,
    project_id: str = "",
    workspace: "str | os.PathLike[str] | None" = None,
) -> bool:
    """Reset a feature to ready when RCA confirms all failures were infra-caused.

    Named entry-point required by F-R7-479 AC:
    ``bob3.rca_infra_recovery.reset_feature_from_infra_error``.

    Orchestrates the full second-line defense:

    1. Calls ``analyze_infra_causation`` to determine whether all failures
       were infrastructure-caused.
    2. If ``infra_only``: harvests any novel pattern from stderr tails,
       appends it to ``config/spawn_retry.yaml``, then resets the feature to
       ``ready`` with ``refinement_attempts=0``.
    3. If not ``infra_only``: returns False without touching the database.

    Parameters
    ----------
    feature_id:
        UUID of the feature to potentially reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature in the DB.
    project_id:
        Project identifier passed through to ``auto_reset_if_infra``.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    True
        Feature was reset to ready (infra_only verdict confirmed).
    False
        Feature was NOT reset (non-infra failures detected).

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

    return auto_reset_if_infra(
        feature_id=feature_id,
        project_id=project_id,
        db_update_fn=db_update_fn,
        workspace=workspace,
    )


def reset_feature_on_infra_only(
    feature_id: str,
    db_update_fn,
    project_id: str = "",
    workspace: "str | os.PathLike[str] | None" = None,
) -> bool:
    """Reset a feature to ready when the RCA verdict is infra_only.

    Named entry-point required by AC: ``bob3.rca_infra_recovery.reset_feature_on_infra_only``.
    Second-line defense (F-R7-479): before the orchestrator transitions a feature
    to ``needs_human``, this function checks whether ALL failures were
    infrastructure-caused and, if so, resets the feature to ``ready`` with
    ``refinement_attempts=0`` and auto-learns any novel error signature.

    Parameters
    ----------
    feature_id:
        UUID of the feature to potentially reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature in the DB.
    project_id:
        Project identifier passed through to ``auto_reset_if_infra``.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    True
        Feature was reset to ready (infra_only verdict confirmed).
    False
        Feature was NOT reset (non-infra failures detected).

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

    return auto_reset_if_infra(
        feature_id=feature_id,
        project_id=project_id,
        db_update_fn=db_update_fn,
        workspace=workspace,
    )
