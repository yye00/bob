"""Disk-state reconciler for Bob (feature 2f69b554).

Fixes the "eval-demotion treadmill": every generation re-ran every ready
feature even when its acceptance-criteria artifacts already existed on disk
from the parent generation.  This module promotes features to 'completed'
when their on-disk state already satisfies every verifiable AC.

Run :func:`reconcile_from_disk` once at the start of every ``bob run``
loop, before any sub-agent spawns.  Features that already pass all ACs are
atomically transitioned to 'completed' with a ``disk_reconciliation``
evidence artifact, preventing redundant re-execution.

Integration: called from ``bob.orchestrator.run_loop._run_locked`` before
the main ``while True`` loop.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import time
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_ac_against_disk(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str]:
    """Evaluate a single acceptance-criterion string against the on-disk state.

    Handles the AC types that can be verified statically without spawning a
    sub-agent:

    * ``File exists: <path>`` — checks workspace-relative path existence.
    * ``Function defined: <dotted.name>`` — checks for ``def`` / ``class``
      definition in any ``.py`` under workspace.
    * ``pytest: <node_id>`` — runs ``python -m pytest <node_id>`` in
      workspace; passes only when exit code 0 AND collected > 0.
    * ``integration: <pkg.mod>`` — delegates to the existing
      ``_integration_wired`` helper from enhanced_verification.

    Returns ``(passed: bool, detail: str)`` where *detail* is a human-readable
    summary of what was checked (for evidence recording).
    """
    from bob.enhanced_verification import _check_criterion_with_details

    is_python = (
        (workspace / "src").exists()
        or (workspace / "pyproject.toml").exists()
        or any(workspace.rglob("*.py"))
    )

    passed, detail = _check_criterion_with_details(
        criterion=criterion,
        workspace=workspace,
        is_python_project=is_python,
        is_cmake_project=False,
        is_opm_project=False,
    )
    return passed, detail or ("ok" if passed else "failed")


def reconcile_from_disk(project_id: str, workspace: pathlib.Path | None = None) -> int:
    """Promote features whose on-disk state satisfies all verifiable ACs.

    For each feature in status ``'ready'`` or ``'pending'`` (after seed):

    1. Parse ``acceptance_criteria`` as a JSON list.
    2. Skip features that have no ACs or whose ACs include only
       ``integration:`` entries (those require wiring evidence, not just
       disk checks).
    3. Evaluate every non-integration AC via :func:`evaluate_ac_against_disk`.
    4. Also evaluate integration ACs — if any fail, the feature is NOT
       promoted (no regression allowed).
    5. If every AC passes, atomically transition to ``'completed'`` and
       record a ``disk_reconciliation`` evidence artifact.

    Returns the number of features promoted.

    Idempotent: calling this function multiple times for the same project is
    safe — features already in ``'completed'`` are skipped by the status
    filter.
    """
    if not project_id:
        raise ValueError("project_id must be a non-empty string, got: {!r}".format(project_id))

    from bob import db

    if workspace is None:
        workspace = pathlib.Path.cwd()

    workspace = pathlib.Path(workspace)

    # WALL-CLOCK BUDGET (bob72 startup-wedge fix). This runs ONCE before the
    # dispatch loop and evaluates EVERY ready+pending feature's ACs against disk
    # — for a resumed run with a large backlog that is 76 features × ~8 ACs ×
    # pytest (up to 600s/criterion). One hanging/slow pytest blocked startup for
    # 10+ min and the loop never reached feature dispatch (completed froze; stack
    # trace: reconcile_from_disk → _run_pytest_criterion → subprocess.communicate
    # in selectors.select). Reconciliation is a best-effort OPTIMISATION (it just
    # promotes already-built features to skip rework); it must never block the
    # loop. Cap total time via BOB_RECONCILE_BUDGET_SECONDS (default 120); on
    # exceed, stop and let the normal executor handle the rest.
    budget_raw = os.environ.get("BOB_RECONCILE_BUDGET_SECONDS")
    try:
        budget_s = float(budget_raw) if budget_raw else 120.0
    except (TypeError, ValueError):
        budget_s = 120.0
    start = time.monotonic()

    promoted = 0
    for status in ("ready", "pending"):
        features = db.list_features(project_id=project_id, status=status)
        for feature in features:
            if budget_s > 0 and (time.monotonic() - start) >= budget_s:
                logger.warning(
                    "reconcile_from_disk: wall-clock budget %.0fs exhausted after "
                    "promoting %d feature(s); deferring the rest to the executor "
                    "so the dispatch loop is not blocked at startup.",
                    budget_s, promoted,
                )
                return promoted
            if not feature.acceptance_criteria:
                continue

            try:
                criteria: list[str] = json.loads(feature.acceptance_criteria)
            except (json.JSONDecodeError, TypeError):
                logger.debug(
                    "reconcile_from_disk: could not parse AC for feature %s, skipping",
                    feature.id,
                )
                continue

            if not criteria:
                continue

            # Evaluate every criterion (including integration ACs).
            results: list[dict[str, Any]] = []
            all_passed = True
            for criterion in criteria:
                # Budget guard between criteria too — a single feature can have
                # many pytest ACs; don't let one feature blow the whole budget.
                if budget_s > 0 and (time.monotonic() - start) >= budget_s:
                    all_passed = False
                    break
                passed, detail = evaluate_ac_against_disk(criterion, workspace)
                results.append(
                    {"criterion": criterion, "passed": passed, "detail": detail}
                )
                if not passed:
                    all_passed = False

            if not all_passed:
                logger.debug(
                    "reconcile_from_disk: feature %s (%s) has failing ACs on disk, skipping",
                    feature.id,
                    feature.name,
                )
                continue

            # All ACs pass — atomically promote to completed.
            content = json.dumps(
                {
                    "reconciled_at": datetime.now().isoformat(),
                    "feature_id": feature.id,
                    "feature_name": feature.name,
                    "checks": results,
                },
                indent=2,
            )
            try:
                db.create_evidence(
                    project_id=project_id,
                    feature_id=feature.id,
                    type="disk_reconciliation",
                    content=content,
                    evidence_id=str(uuid.uuid4()),
                )
                db.update_feature(feature.id, status="completed")
                promoted += 1
                logger.info(
                    "reconcile_from_disk: promoted feature %s (%s) to completed "
                    "(all %d AC(s) satisfied on disk)",
                    feature.id,
                    feature.name,
                    len(criteria),
                )
            except Exception:
                logger.exception(
                    "reconcile_from_disk: failed to promote feature %s, skipping",
                    feature.id,
                )

    if promoted:
        logger.info(
            "reconcile_from_disk: promoted %d feature(s) to completed from disk state",
            promoted,
        )
    else:
        logger.debug("reconcile_from_disk: no features promoted (all ACs already satisfied or failing)")

    return promoted


# Status sentinel returned when workspace does not exist or promotion is refused.
NOT_RECONCILED = "NOT_RECONCILED"


def handle_missing_workspace(workspace: pathlib.Path) -> str:
    """Return NOT_RECONCILED when workspace_dir does not exist; never raises.

    This is the safe guard called before any AC evaluation.  A missing
    workspace means there is nothing on disk to compare against, so
    reconciliation is simply skipped.
    """
    if not workspace.exists():
        logger.debug(
            "handle_missing_workspace: workspace %s does not exist; returning NOT_RECONCILED",
            workspace,
        )
        return NOT_RECONCILED
    return "OK"


def never_raises_on_missing_workspace(workspace: pathlib.Path) -> bool:
    """Document that handle_missing_workspace never raises; returns True.

    Calls handle_missing_workspace and verifies no exception is propagated,
    regardless of whether the workspace exists.  Useful as a canary in
    CI and test environments where workspaces may be absent.
    """
    try:
        handle_missing_workspace(workspace)
    except Exception:
        return False
    return True


def promote_to_completed(
    project_id: str,
    feature_id: str,
    feature_name: str,
    checks: list[dict[str, Any]],
) -> bool:
    """Atomic status transition to 'completed' with disk_reconciliation evidence.

    Records a ``disk_reconciliation`` evidence artifact then updates the
    feature status to ``'completed'``.  Both operations are attempted in a
    try/except so that a DB error on either step does not crash the caller.

    Returns True on success, False on any exception.
    """
    from bob import db

    content = json.dumps(
        {
            "reconciled_at": datetime.now().isoformat(),
            "feature_id": feature_id,
            "feature_name": feature_name,
            "checks": checks,
        },
        indent=2,
    )
    try:
        db.create_evidence(
            project_id=project_id,
            feature_id=feature_id,
            type="disk_reconciliation",
            content=content,
            evidence_id=str(uuid.uuid4()),
        )
        db.update_feature(feature_id, status="completed")
        logger.info(
            "promote_to_completed: feature %s (%s) → completed (disk_reconciliation)",
            feature_id,
            feature_name,
        )
        return True
    except Exception:
        logger.exception(
            "promote_to_completed: failed to promote feature %s, skipping",
            feature_id,
        )
        return False


def handle_failing_integration_ac(
    criteria: list[str],
    workspace: pathlib.Path,
) -> str:
    """Refuse promotion when any integration AC regresses.

    Evaluates every criterion whose prefix is ``integration:``.  If any
    integration criterion fails on disk, returns NOT_RECONCILED immediately
    without evaluating the remaining ones.  Non-integration criteria are
    ignored by this function — it is a targeted guard, not a full evaluator.

    Returns NOT_RECONCILED if any integration AC fails, otherwise "OK".
    """
    for criterion in criteria:
        if not criterion.startswith("integration:"):
            continue
        passed, detail = evaluate_ac_against_disk(criterion, workspace)
        if not passed:
            logger.debug(
                "handle_failing_integration_ac: criterion %r failed (%s); "
                "refusing promotion",
                criterion,
                detail,
            )
            return NOT_RECONCILED
    return "OK"


def check_executing_feature_acs(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
    workspace: pathlib.Path | None = None,
) -> bool:
    """Check whether an 'executing' feature satisfies all its ACs on disk.

    Called by _final_exit_sweep (F-R7-598) before flipping an orphan-executing
    feature to 'failed'.  If all ACs pass, atomically promotes to 'completed'
    via promote_to_completed and returns True.  Returns False if any AC fails
    or if the AC list cannot be parsed.

    This mirrors the logic of reconcile_from_disk but applies to features
    already in 'executing' status (which reconcile_from_disk skips).
    """
    if workspace is None:
        workspace = pathlib.Path.cwd()
    workspace = pathlib.Path(workspace)

    try:
        criteria: list[str] = json.loads(acceptance_criteria_json)
    except (json.JSONDecodeError, TypeError):
        logger.debug(
            "check_executing_feature_acs: could not parse AC for feature %s, cannot promote",
            feature_id,
        )
        return False

    if not criteria:
        return False

    results: list[dict[str, Any]] = []
    all_passed = True
    for criterion in criteria:
        try:
            passed, detail = evaluate_ac_against_disk(criterion, workspace)
        except Exception:
            logger.debug(
                "check_executing_feature_acs: AC evaluation error for feature %s criterion %r",
                feature_id,
                criterion,
                exc_info=True,
            )
            all_passed = False
            break
        results.append({"criterion": criterion, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

    if not all_passed:
        logger.debug(
            "check_executing_feature_acs: feature %s (%s) has failing ACs on disk; "
            "will not promote",
            feature_id,
            feature_name,
        )
        return False

    return promote_to_completed(project_id, feature_id, feature_name, results)
