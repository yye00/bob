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

import bob.orchestrator.rca_infra_recovery as _rca
from bob.orchestrator.rca_infra_recovery import (
    _append_discovered_pattern,
    auto_reset_if_infra,
    classify_attempts,
    harvest_novel_pattern,
)

__all__ = [
    "analyze_infra_failures",
    "append_novel_signature",
    "append_signature_to_spawn_retry",
    "append_transient_signature",
    "check_infra_only",
    "diagnose_infra_failure",
    "is_infra_only",
    "learn_signature",
    "reset_feature_on_infra_only",
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


def diagnose_infra_failure(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Diagnose whether a feature's failure history is infra-caused.

    Second-line defense entry point (F-R7-479): called BEFORE the orchestrator
    transitions a feature to ``needs_human``. Returns a verdict string that the
    caller uses to decide whether to auto-reset or escalate.

    This is the canonical entry point for the RCA diagnostic step — it wraps
    ``analyze_infra_failures`` with a clearer, more intent-revealing name.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to the current directory.

    Returns
    -------
    ``"infra_only"``
        All failures were infrastructure-caused; feature may be auto-reset.
    ``"feature_defect"``
        At least one failure has real-work evidence or a non-infra error.
    ``"mixed"``
        Mix of infra and non-infra failures. Treat as ``feature_defect``.

    Raises
    ------
    ValueError
        If ``feature_id`` is None, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a string.
    """
    return analyze_infra_failures(feature_id, workspace=workspace)


def reset_feature_on_infra_only(
    feature_id: str,
    db_update_fn,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Reset a feature to ``ready`` if and only if all failures were infra-caused.

    Combines the RCA diagnostic (``diagnose_infra_failure``) with the reset
    action in a single call. If the verdict is ``infra_only``, the feature is
    reset to ``ready`` with ``refinement_attempts=0`` via ``db_update_fn``.

    Parameters
    ----------
    feature_id:
        UUID of the feature to inspect and potentially reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
        Matches the signature of ``bob.db.update_feature``.
    workspace:
        Path to the feature workspace directory. Defaults to the current directory.

    Returns
    -------
    True
        Feature was reset to ``ready`` (verdict was ``infra_only``).
    False
        Feature was NOT reset (verdict was ``feature_defect`` or ``mixed``).

    Raises
    ------
    ValueError
        If ``feature_id`` is None, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a string or ``db_update_fn`` is not callable.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")
    if not callable(db_update_fn):
        raise TypeError(f"db_update_fn must be callable, got {type(db_update_fn).__name__}")

    verdict = diagnose_infra_failure(feature_id, workspace=workspace)
    if verdict == "infra_only":
        db_update_fn(feature_id, status="ready", refinement_attempts=0)
        return True
    return False


def append_novel_signature(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel infra error signature discovered by the RCA layer.

    When a brand-new infra signature slips past the first-line spawn-layer
    guard (F-R7-478), the RCA layer calls this function to persist the pattern
    so future runs catch it. The system self-heals WITHOUT a human edit.

    This is an alias for ``learn_signature`` / ``append_transient_signature``
    with the AC-mandated name ``append_novel_signature``.

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
    learn_signature(pattern, feature_id)


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


def check_infra_only(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None" = None,
) -> bool:
    """Return True when all known failure attempts were infrastructure-caused.

    AC-required entry point for F-R7-479. Second-line defense predicate called
    by the orchestrator BEFORE transitioning a feature to ``needs_human``. When
    True, the feature should be auto-reset to ``ready`` rather than escalated.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

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


def append_signature_to_spawn_retry(
    pattern: str,
    feature_id: str,
) -> None:
    """Append a novel infra error signature to ``config/spawn_retry.yaml``.

    AC-required entry point for F-R7-479. When the RCA layer discovers a new
    error pattern that slipped past the first-line spawn-layer guard (F-R7-478),
    this function persists it so future runs catch it automatically. The system
    self-heals WITHOUT a human edit.

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
