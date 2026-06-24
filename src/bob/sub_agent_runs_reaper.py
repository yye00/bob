"""Zombie sub_agent_runs reaper — close 'running' rows whose target feature is terminal.

sub_agent_runs.status='running' rows can outlive the actual subagent process
when the R9-001 update-before-unwind path is bypassed (SIGKILL, OOM, container
restart). Example: row 7fbefda3 stayed 'running' for 14+ hours while its target
feature 590b9008 had been 'completed' since 07:26 local.

This module provides the canonical public API for zombie run reaping, used both
directly and by bob.orchestrator.

Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

Public API
----------
reap_zombie_runs(project_id)
    Find and reap all zombie sub_agent_runs for the project. Returns list of
    reaped run IDs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bob import db

logger = logging.getLogger(__name__)

_TERMINAL_FEATURE_STATUSES = ("completed", "needs_human", "regression", "failed")


def reap_zombie_runs(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is already terminal.

    Joins sub_agent_runs (status='running') against features and marks any row
    whose target_id references a feature in a terminal state as status='timeout'
    with a completion timestamp.

    Raises ValueError for invalid project_id (None or empty string).

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').

    Raises:
        ValueError: If project_id is None or empty.
    """
    if project_id is None or (isinstance(project_id, str) and not project_id.strip()):
        raise ValueError(f"project_id must be a non-empty string, got {project_id!r}")

    running_runs = db.query_agent_runs(project_id=project_id, status="running")

    candidates = [r for r in running_runs if r.target_id is not None]
    if not candidates:
        return []

    terminal_feature_ids: set[str] = set()
    for status in _TERMINAL_FEATURE_STATUSES:
        for feature in db.list_features(project_id=project_id, status=status):
            terminal_feature_ids.add(feature.id)

    now = datetime.now(timezone.utc)
    reaped_ids: list[str] = []
    for run in candidates:
        if run.target_id not in terminal_feature_ids:
            continue
        logger.info(
            "ZOMBIE_REAPER: closing run %s (purpose=%s target_id=%s) as timeout",
            run.id[:8],
            run.purpose,
            run.target_id[:8] if run.target_id else None,
        )
        try:
            db.update_agent_run(run.id, status="timeout", completed_at=now)
            reaped_ids.append(run.id)
        except Exception:
            logger.warning(
                "ZOMBIE_REAPER: failed to reap run %s; skipping",
                run.id[:8],
                exc_info=True,
            )

    return reaped_ids
