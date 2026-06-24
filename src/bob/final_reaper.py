"""Final reaper sweep — flips orphan 'executing' rows to 'failed' on orchestrator exit.

Implements the hot-fix for the pattern where orchestrator exits ALL_BLOCKED or
BUDGET_EXCEEDED while sub-agents have already died, leaving rows stuck in
status='executing' forever and polluting inter-gen status reports.

Public function
---------------
sweep_orphans_on_exit(project_id)
    Invoke immediately before _run_locked returns its LoopTermination.
    Calls sweep_orphan_subagents (the same reaper that runs in the main loop
    tick) then flips any remaining 'executing' rows whose PID is gone to
    'failed' with reason 'orchestrator_exit_during_execution'.
    Idempotent and safe.
"""

from __future__ import annotations

import logging

from bob import db

logger = logging.getLogger(__name__)

_EXIT_REASON = "orchestrator_exit_during_execution"


def _get_subagent_reaper():
    """Lazy import of subagent_reaper to break the circular import with orchestrator.__init__."""
    import importlib  # noqa: PLC0415
    return importlib.import_module("bob.orchestrator.subagent_reaper")


def sweep_orphan_subagents():
    """Module-level proxy so patch('bob.final_reaper.sweep_orphan_subagents') works in tests."""
    return _get_subagent_reaper().sweep_orphan_subagents()


def find_subagent_pid_for_feature(feature_id):
    """Module-level proxy so patch('bob.final_reaper.find_subagent_pid_for_feature') works in tests."""
    return _get_subagent_reaper().find_subagent_pid_for_feature(feature_id)


def sweep_orphans_on_exit(project_id: str) -> list[str]:
    """Sweep orphan executing rows immediately before the orchestrator returns LoopTermination.

    Steps:
    1. Run sweep_orphan_subagents() to reap any subagent PIDs for features
       already in terminal states (idempotent; same as the main-loop tick).
    2. Query all features in status='executing' for the project.
    3. For each, check whether a live PID is still attached. If none is found
       (the sub-agent has already exited), flip status to 'failed' with
       last_improvement_type='orchestrator_exit_during_execution'.

    The sweep is idempotent: a second call with the same DB state produces zero
    additional writes. Per-feature errors are caught and logged; the sweep
    continues to the remaining rows so a single broken row never aborts cleanup.

    Args:
        project_id: UUID of the project whose orphan executing rows to sweep.
                    Must be a non-empty string.

    Returns:
        List of feature IDs that were flipped to 'failed'.

    Raises:
        ValueError: If project_id is None or not a string.
    """
    if project_id is None or not isinstance(project_id, str):
        raise ValueError(
            f"sweep_orphans_on_exit: project_id must be a non-empty string, "
            f"got {project_id!r}"
        )

    # Step 1: reap subagent PIDs for terminal-state features (idempotent).
    try:
        reaped = sweep_orphan_subagents()
        if reaped:
            logger.info(
                "sweep_orphans_on_exit: sweep_orphan_subagents reaped %d item(s): %s",
                len(reaped),
                reaped,
            )
    except Exception:
        logger.warning(
            "sweep_orphans_on_exit: sweep_orphan_subagents raised; continuing",
            exc_info=True,
        )

    # Step 2: find all still-executing rows.
    try:
        executing_features = db.list_features(project_id=project_id, status="executing")
    except Exception:
        logger.warning(
            "sweep_orphans_on_exit: failed to query executing features for project %s",
            project_id,
            exc_info=True,
        )
        return []

    flipped: list[str] = []

    for feature in executing_features:
        try:
            live_pids = find_subagent_pid_for_feature(feature.id)
        except Exception:
            logger.warning(
                "sweep_orphans_on_exit: PID lookup failed for feature %s; skipping",
                feature.id[:8],
                exc_info=True,
            )
            continue

        if live_pids:
            logger.debug(
                "sweep_orphans_on_exit: feature %s has live PIDs %s; skipping",
                feature.id[:8],
                live_pids,
            )
            continue

        # No live PID — flip to failed.
        try:
            db.update_feature(
                feature.id,
                status="failed",
                last_improvement_type=_EXIT_REASON,
            )
            flipped.append(feature.id)
            logger.info(
                "sweep_orphans_on_exit: flipped orphan executing feature %s to failed",
                feature.id[:8],
            )
        except Exception:
            logger.warning(
                "sweep_orphans_on_exit: failed to flip feature %s to failed",
                feature.id[:8],
                exc_info=True,
            )

    if flipped:
        logger.info(
            "sweep_orphans_on_exit: flipped %d orphan executing feature(s) to failed",
            len(flipped),
        )

    return flipped
