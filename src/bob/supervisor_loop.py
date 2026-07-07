"""Unattended-build supervisor loop — auto-resume after a would-be QUEUE_DRAINED exit.

Feature 27e4c777.

Regression this guards against
------------------------------
``bob run --all`` exits (code 2, ``QUEUE_DRAINED`` / ``ALL_BLOCKED``) whenever a
scheduling pass finds no *immediately*-claimable feature — even when pending
features exist that ARE runnable, or that become runnable once a transient-failed
sibling is reset. For an unattended dark factory this halts the whole build until
a human re-runs, which meant re-running ``bob run --all`` by hand every few
minutes.

The fix
-------
``auto_resume_run`` inspects the full feature set at a would-be drain and decides
whether the orchestrator should resume rather than exit:

  * If any pending feature has all deps completed → **resume** (no reset needed).
  * If a pending feature is blocked only by transient/failed **non-needs_human**
    siblings → **reset those failures to pending and resume**.
  * A live ``executing`` feature is NEVER reset (partial WIP is preserved), and
    its presence keeps the loop alive.
  * Terminate only when there is no pending work at all (``QUEUE_EMPTY``) or every
    remaining pending feature is transitively blocked by a ``needs_human`` feature
    (``BLOCKED_ON_HUMAN``).

The pure decision function (``auto_resume_run``) is DB-free and fully unit
testable; ``supervise_run`` wires it to :mod:`bob.db` for the live CLI path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)

# A completed dependency is the only thing that unblocks a dependent outright.
_COMPLETED_STATUS = "completed"

# Statuses that make a feature immediately eligible for dispatch.
RUNNABLE_STATUSES = frozenset({"ready", "pending"})

# Failure statuses that are recoverable by resetting the feature back to pending.
# These are transient / work-loss failures — NOT human-gated ones.
RECOVERABLE_FAILURE_STATUSES = frozenset({"failed", "timeout", "interrupted"})

# A live executing feature must never be reset — its partial work is in flight.
_LIVE_STATUS = "executing"

# Human-gated status: a feature (or its transitive deps) in this state is not
# recoverable without human action.
_NEEDS_HUMAN_STATUS = "needs_human"


@dataclass
class ResumeDecision:
    """Outcome of an auto-resume evaluation at a would-be QUEUE_DRAINED exit.

    Attributes:
        should_resume: True when the orchestrator should keep running rather than
            exit. When True, ``reset_feature_ids`` (possibly empty) have already
            been reset to 'pending' if a ``reset_fn`` was supplied.
        reset_feature_ids: Recoverable transient-failed sibling ids that were
            reset to 'pending' to unblock pending work, in input order.
        terminate_reason: ``None`` when resuming; otherwise a stable label —
            ``"QUEUE_EMPTY"`` (no pending work remains) or ``"BLOCKED_ON_HUMAN"``
            (all remaining pending work is transitively human-gated).
    """

    should_resume: bool
    reset_feature_ids: list[str] = field(default_factory=list)
    terminate_reason: str | None = None


def _get(feature: Any, name: str, default: Any = None) -> Any:
    if isinstance(feature, dict):
        return feature.get(name, default)
    return getattr(feature, name, default)


def _feature_id(feature: Any) -> str:
    fid = _get(feature, "id")
    if fid is None or fid == "":
        raise ValueError(f"feature has no unique id: {feature!r}")
    return str(fid)


def _depends_on(feature: Any) -> list[str]:
    deps = _get(feature, "depends_on") or []
    if isinstance(deps, str):
        return [deps]
    return list(deps)


def auto_resume_run(
    features: Sequence[Any],
    reset_fn: Callable[[str], Any] | None = None,
) -> ResumeDecision:
    """Decide whether a would-be QUEUE_DRAINED exit should instead resume.

    This is the core supervisor decision. It is pure with respect to the input
    ``features`` snapshot; the only side effect is invoking ``reset_fn`` for each
    recoverable transient-failed sibling that unblocks pending work.

    Args:
        features: The full feature set for the project. Each item is a mapping or
            object exposing ``id``, ``status`` and optional ``depends_on``.
        reset_fn: Optional callback invoked with each recoverable feature id that
            is reset to 'pending'. When omitted, the ids are still reported in the
            returned decision but no persistence happens (pure evaluation).

    Returns:
        A :class:`ResumeDecision`.

    Raises:
        ValueError: if ``features`` is not a list/tuple, any feature lacks an id,
            or ``reset_fn`` is provided but not callable.
    """
    if not isinstance(features, (list, tuple)):
        raise ValueError(
            f"features must be a list or tuple, got {type(features).__name__}"
        )
    if reset_fn is not None and not callable(reset_fn):
        raise ValueError("reset_fn must be callable or None")

    # Index status by unique id (validates ids too).
    status_by_id: dict[str, str] = {}
    for feature in features:
        status_by_id[_feature_id(feature)] = _get(feature, "status")

    pending = [f for f in features if _get(f, "status") in RUNNABLE_STATUSES]
    has_executing = any(s == _LIVE_STATUS for s in status_by_id.values())

    if not pending:
        # No claimable work left. If something is still executing, keep the loop
        # alive so it can reap that work; otherwise the queue is genuinely empty.
        if has_executing:
            return ResumeDecision(should_resume=True)
        return ResumeDecision(should_resume=False, terminate_reason="QUEUE_EMPTY")

    # Determine, per dependency, whether it is recoverable (transient failure that
    # is NOT transitively human-gated). Cache to avoid recomputation.
    _recoverable_cache: dict[str, bool] = {}

    def _is_recoverable(dep_id: str, _stack: frozenset[str]) -> bool:
        """True if resetting/rerunning dep_id could eventually complete it."""
        if dep_id in _recoverable_cache:
            return _recoverable_cache[dep_id]
        if dep_id in _stack:
            # Dependency cycle — treat as non-recoverable to avoid infinite loops.
            return False
        status = status_by_id.get(dep_id)
        result: bool
        if status == _NEEDS_HUMAN_STATUS:
            result = False
        elif status == _COMPLETED_STATUS:
            result = True
        elif status == _LIVE_STATUS or status in RUNNABLE_STATUSES:
            # In flight or already queued — will progress on its own.
            result = True
        elif status in RECOVERABLE_FAILURE_STATUSES:
            # Recoverable only if ITS deps are not human-gated.
            dep_feat = next((f for f in features if _feature_id(f) == dep_id), None)
            sub_deps = _depends_on(dep_feat) if dep_feat is not None else []
            result = all(
                _is_recoverable(d, _stack | {dep_id}) for d in sub_deps
            )
        else:
            # Unknown status — conservatively non-recoverable.
            result = False
        _recoverable_cache[dep_id] = result
        return result

    # A pending feature is "advanceable" if every dep is recoverable (i.e. not
    # transitively blocked by a needs_human feature).
    any_advanceable = False
    for feat in pending:
        deps = _depends_on(feat)
        if all(_is_recoverable(d, frozenset()) for d in deps):
            any_advanceable = True
            break

    if not any_advanceable:
        # Every pending feature is transitively blocked by human-gated work.
        return ResumeDecision(
            should_resume=False, terminate_reason="BLOCKED_ON_HUMAN"
        )

    # Collect the recoverable transient-failed siblings to reset — in input order.
    # These are features whose OWN reset would help an advanceable pending item.
    reset_ids: list[str] = []
    for feature in features:
        fid = _feature_id(feature)
        status = status_by_id.get(fid)
        if status in RECOVERABLE_FAILURE_STATUSES and _is_recoverable(
            fid, frozenset()
        ):
            reset_ids.append(fid)

    if reset_fn is not None:
        for fid in reset_ids:
            try:
                reset_fn(fid)
            except Exception:
                logger.warning(
                    "auto_resume_run: reset_fn failed for feature %s; "
                    "continuing (it will be retried next drain)",
                    fid,
                    exc_info=True,
                )

    if reset_ids:
        logger.info(
            "auto_resume_run: resuming — reset %d recoverable feature(s): %s",
            len(reset_ids),
            ", ".join(reset_ids),
        )
    else:
        logger.info("auto_resume_run: resuming — runnable pending work remains")

    return ResumeDecision(should_resume=True, reset_feature_ids=reset_ids)


def supervise_run(project_id: str) -> ResumeDecision:
    """Live wiring of :func:`auto_resume_run` against :mod:`bob.db`.

    Loads the project's features, evaluates the auto-resume decision, and — when
    resuming — resets each recoverable transient-failed feature to 'pending' in
    the database. NEVER resets an 'executing' feature (WIP preserved).

    Args:
        project_id: UUID of the project whose queue drained.

    Returns:
        The :class:`ResumeDecision`.

    Raises:
        ValueError: if ``project_id`` is None or empty.
    """
    if not project_id:
        raise ValueError("project_id must be a non-empty string")

    from bob import db

    rows = db.list_features(project_id=project_id)

    # Feature rows store dependencies in a separate table; project them onto a
    # plain snapshot so the pure decision function can reason about the graph.
    features: list[dict[str, Any]] = []
    for row in rows:
        deps = [d.depends_on_feature_id for d in db.get_feature_dependencies(row.id)]
        features.append({"id": row.id, "status": row.status, "depends_on": deps})

    def _reset(fid: str) -> None:
        db.update_feature(fid, status="pending")

    return auto_resume_run(features, reset_fn=_reset)
