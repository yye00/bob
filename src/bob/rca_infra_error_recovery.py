"""RCA-layer infra-error recovery — second-line defense against false NH (F-R7-479).

F-R7-478 guards the *spawn* layer with a regex set of known transient signatures.
But a brand-new infra signature slips past it. This module adds the second line:
BEFORE the orchestrator transitions a feature to ``needs_human``, the RCA layer
inspects the history of failed attempts and answers — were ALL N attempts
infra-caused?

If the verdict is ``infra_only``: the feature is reset to ``ready`` with
``refinement_attempts=0`` and the discovered novel signature is auto-appended to
``config/spawn_retry.yaml`` so the first-line guard catches it next time — the
system learns the new transient pattern WITHOUT a human edit.

Source directive: user — "claude cli having a bad day just retry it, do not count
it as needs human."

This module is a thin, validated façade over the orchestrator-layer engine in
``bob.orchestrator.rca_infra_recovery``; it re-uses ``classify_attempts`` and
``auto_reset_if_infra`` rather than re-implementing the multi-signal heuristics.
"""

from __future__ import annotations

import os

from bob.orchestrator import rca_infra_recovery as _engine
from bob.orchestrator.rca_infra_recovery import Verdict

__all__ = [
    "classify_attempts_infra_only",
    "recover_infra_only_feature",
    "Verdict",
]


def _validate_feature_id(feature_id: str) -> None:
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty or whitespace")


def classify_attempts_infra_only(
    feature_id: str,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when ALL known failure attempts were infrastructure-caused.

    This is the second-line defense predicate, called by the orchestrator BEFORE
    transitioning a feature to ``needs_human``. When True, the feature should be
    auto-reset to ``ready`` rather than escalated to a human.

    Classification is delegated to ``classify_attempts`` (orchestrator layer),
    which applies multi-signal heuristics: stderr-tail pattern matching against
    known infra signatures, detection of real work events in progress.jsonl,
    cross-feature crash clustering, and agent-log size heuristics.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose failure history should be inspected.
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    bool
        True if the RCA verdict is ``infra_only``; False for ``feature_defect``
        or ``mixed``.

    Raises
    ------
    ValueError
        If ``feature_id`` is None, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a string.
    """
    _validate_feature_id(feature_id)
    verdict: Verdict = _engine.classify_attempts(feature_id, workspace=workspace)
    return verdict == "infra_only"


def recover_infra_only_feature(
    feature_id: str,
    db_update_fn,
    project_id: str = "",
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Reset a feature to ready and auto-learn its novel infra signature.

    Orchestrates the full second-line defense (F-R7-479):

    1. Determines whether all failures were infrastructure-caused.
    2. If ``infra_only``: harvests any novel pattern from the stderr tails,
       appends it to ``config/spawn_retry.yaml``, then resets the feature to
       ``ready`` with ``refinement_attempts=0`` (subject to the per-generation
       auto-reset cap enforced by the engine).
    3. If not ``infra_only``: returns False without touching the database.

    Parameters
    ----------
    feature_id:
        UUID of the feature to potentially reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature in the DB.
        Matches the signature of ``bob.db.update_feature``.
    project_id:
        Project identifier (passed through to ``auto_reset_if_infra``).
    workspace:
        Path to the feature workspace directory. Defaults to current directory.

    Returns
    -------
    bool
        True if the feature was reset to ready (infra_only verdict confirmed);
        False if it was NOT reset (non-infra failures, or reset cap reached).

    Raises
    ------
    ValueError
        If ``feature_id`` is None, empty, or whitespace-only.
    TypeError
        If ``feature_id`` is not a string, or ``db_update_fn`` is not callable.
    """
    _validate_feature_id(feature_id)
    if not callable(db_update_fn):
        raise TypeError(
            f"db_update_fn must be callable, got {type(db_update_fn).__name__}"
        )

    return _engine.auto_reset_if_infra(
        feature_id=feature_id,
        project_id=project_id,
        db_update_fn=db_update_fn,
        workspace=workspace,
    )
